import base64
import hashlib
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, quantiles
from typing import Any, Literal

from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.sika_route import (
    KASPA_POLICY_HASH_LABEL,
    MarketRoundInput,
    list_demo_scenarios,
    run_all_demo_rounds,
    run_demo_scenario,
    run_market_round,
)


# DB path is overridable so tests can use an isolated database.
def _default_db_path() -> str:
    if os.environ.get("BIOVAULT_DB"):
        return os.environ["BIOVAULT_DB"]
    # Vercel/Lambda filesystems are read-only outside /tmp.
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return "/tmp/biovault.db"
    return str(Path(__file__).resolve().parents[1] / "biovault.db")


DB_PATH = Path(_default_db_path())

# Demo-only: deterministic Fernet key derived from a fixed phrase.
# Not production-safe — replace with a secrets manager in any real deployment.
FERNET_KEY = base64.urlsafe_b64encode(
    hashlib.sha256(b"biovault-hackathon-demo-key").digest()
)
fernet = Fernet(FERNET_KEY)

# Capability operations. Identity is proven by a principal token; these scope
# what an authenticated principal may do to a specific artifact.
Operation = Literal["read", "derive", "revoke", "grant", "redact"]
Decision = Literal["allow", "deny"]


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class GrantRequest(BaseModel):
    subject_user_id: str
    operation: Operation = "read"
    expires_at: str | None = None
    purpose: str = "unspecified"


class RevokeRequest(BaseModel):
    purpose: str = "source_revocation"


class DeriveRequest(BaseModel):
    title: str = "Derived Artifact"
    parent_artifact_ids: list[str]
    redacted: bool = False
    # Parents whose content is excluded from a redacted derivation.
    redact_parent_ids: list[str] = []
    reason: str = "unspecified"


# ---------------------------------------------------------------------------
# Crypto / hashing helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


def mint_token() -> str:
    return secrets.token_urlsafe(24)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def content_hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()[:16]


def encrypt(plaintext: str) -> str:
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def _add_column(conn: sqlite3.Connection, table: str, coldef: str) -> None:
    """Idempotently add a column to an existing table (lightweight migration)."""
    col = coldef.split()[0]
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                team TEXT NOT NULL,
                token_hash TEXT
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('source', 'derived')),
                encrypted_content TEXT NOT NULL,
                sensitivity TEXT NOT NULL CHECK (
                    sensitivity IN ('public', 'internal', 'restricted', 'confidential')
                ),
                status TEXT NOT NULL CHECK (
                    status IN ('active', 'revoked', 'quarantined', 'redacted')
                ),
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS capability_grants (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                expires_at TEXT,
                revoked INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS lineage_edges (
                parent_artifact_id TEXT NOT NULL,
                child_artifact_id TEXT NOT NULL,
                dependency_type TEXT NOT NULL DEFAULT 'source',
                inclusion TEXT NOT NULL DEFAULT 'included',
                source_hash TEXT,
                created_by TEXT,
                reason TEXT,
                PRIMARY KEY (parent_artifact_id, child_artifact_id)
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                user_id TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('allow', 'deny')),
                reason TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                request_id TEXT,
                detail TEXT
            );

            CREATE TABLE IF NOT EXISTS redaction_attestations (
                id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                created_by TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                detail TEXT NOT NULL
            );
            """
        )

        # Migration: older databases constrained capability_grants.operation to
        # ('read','derive','revoke'). The capability model now includes 'grant'
        # and 'redact'. SQLite cannot drop a CHECK via ALTER, so rebuild the table
        # when the legacy constraint is present (seed wipes data regardless).
        legacy = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='capability_grants'"
        ).fetchone()
        if legacy and "CHECK" in (legacy[0] or ""):
            conn.execute("DROP TABLE capability_grants")
            conn.execute(
                """
                CREATE TABLE capability_grants (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    expires_at TEXT,
                    revoked INTEGER NOT NULL DEFAULT 0
                )
                """
            )

        # Migrations for databases created before these columns existed.
        _add_column(conn, "users", "token_hash TEXT")
        _add_column(conn, "lineage_edges", "dependency_type TEXT NOT NULL DEFAULT 'source'")
        _add_column(conn, "lineage_edges", "inclusion TEXT NOT NULL DEFAULT 'included'")
        _add_column(conn, "lineage_edges", "source_hash TEXT")
        _add_column(conn, "lineage_edges", "created_by TEXT")
        _add_column(conn, "lineage_edges", "reason TEXT")
        _add_column(conn, "audit_events", "request_id TEXT")
        _add_column(conn, "audit_events", "detail TEXT")

        # Evidence patch: indexes for hot lookups.
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_grants_lookup
                ON capability_grants (user_id, artifact_id, operation);
            CREATE INDEX IF NOT EXISTS idx_grants_artifact
                ON capability_grants (artifact_id);
            CREATE INDEX IF NOT EXISTS idx_lineage_parent
                ON lineage_edges (parent_artifact_id);
            CREATE INDEX IF NOT EXISTS idx_lineage_child
                ON lineage_edges (child_artifact_id);
            CREATE INDEX IF NOT EXISTS idx_audit_ts
                ON audit_events (timestamp);
            CREATE INDEX IF NOT EXISTS idx_users_token
                ON users (token_hash);
            """
        )


@asynccontextmanager
async def lifespan(application: FastAPI):  # noqa: ARG001
    init_db()
    yield


def _cors_origins() -> list[str]:
    """Resolve allowed CORS origins from env. Wildcard only when explicitly enabled."""
    if os.environ.get("DEMO_ALLOW_ALL_CORS", "").lower() in ("1", "true", "yes"):
        return ["*"]
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


_cors_allow_origins = _cors_origins()

app = FastAPI(title="BioVault API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins,
    allow_credentials=_cors_allow_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Principal authentication (Patch 1)
# ---------------------------------------------------------------------------

def resolve_principal(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> str:
    """
    Resolve the acting principal from a capability token.

    Identity is NEVER taken from a caller-supplied user_id. The token is the only
    authority: we hash the presented secret and look up the owning principal.
    Accepts `Authorization: Bearer <token>` (preferred) or a `?token=` query
    param (convenience for curl / Swagger). The query token is still a secret
    capability token, not an identity claim.
    """
    raw: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
    elif token:
        raw = token.strip()

    if not raw:
        raise HTTPException(status_code=401, detail={"reason": "missing_principal_token"})

    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE token_hash = ?", (hash_token(raw),)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail={"reason": "invalid_principal_token"})
    return row["id"]


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def add_user(conn: sqlite3.Connection, user_id: str, name: str, role: str, team: str) -> str:
    """Insert a user, mint a principal token, store only its hash, return plaintext."""
    raw_token = mint_token()
    conn.execute(
        "INSERT INTO users (id, name, role, team, token_hash) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, role, team, hash_token(raw_token)),
    )
    return raw_token


def add_artifact(
    conn: sqlite3.Connection,
    artifact_id: str,
    title: str,
    artifact_type: str,
    content: str,
    sensitivity: str,
    created_by: str,
    status: str = "active",
) -> None:
    conn.execute(
        """
        INSERT INTO artifacts
            (id, title, type, encrypted_content, sensitivity, status, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (artifact_id, title, artifact_type, encrypt(content), sensitivity, status, created_by, now_iso()),
    )


def add_grant(
    conn: sqlite3.Connection,
    user_id: str,
    artifact_id: str,
    operation: Operation,
    expires_at: str | None = None,
) -> str:
    grant_id = f"grant_{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO capability_grants
            (id, user_id, artifact_id, operation, expires_at, revoked)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (grant_id, user_id, artifact_id, operation, expires_at),
    )
    return grant_id


def grant_many(
    conn: sqlite3.Connection,
    user_id: str,
    artifact_ids: list[str],
    operations: list[Operation],
) -> None:
    for artifact_id in artifact_ids:
        for operation in operations:
            add_grant(conn, user_id, artifact_id, operation)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_artifact(conn: sqlite3.Connection, artifact_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()


def get_direct_edges(conn: sqlite3.Connection, child_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM lineage_edges WHERE child_artifact_id = ?", (child_id,)
    ).fetchall()


def get_transitive_parents(conn: sqlite3.Connection, artifact_id: str) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    seen: set[str] = set()
    stack = [artifact_id]
    while stack:
        current = stack.pop()
        parents = conn.execute(
            """
            SELECT a.* FROM artifacts a
            JOIN lineage_edges e ON e.parent_artifact_id = a.id
            WHERE e.child_artifact_id = ?
            """,
            (current,),
        ).fetchall()
        for parent in parents:
            if parent["id"] not in seen:
                seen.add(parent["id"])
                rows.append(parent)
                stack.append(parent["id"])
    return rows


def get_transitive_children(conn: sqlite3.Connection, artifact_id: str) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    seen: set[str] = set()
    stack = [artifact_id]
    while stack:
        current = stack.pop()
        children = conn.execute(
            """
            SELECT a.* FROM artifacts a
            JOIN lineage_edges e ON e.child_artifact_id = a.id
            WHERE e.parent_artifact_id = ?
            """,
            (current,),
        ).fetchall()
        for child in children:
            if child["id"] not in seen:
                seen.add(child["id"])
                rows.append(child)
                stack.append(child["id"])
    return rows


def has_grant(
    conn: sqlite3.Connection, user_id: str, artifact_id: str, operation: Operation
) -> bool:
    grant = conn.execute(
        """
        SELECT 1 FROM capability_grants
        WHERE user_id = ?
          AND artifact_id = ?
          AND operation = ?
          AND revoked = 0
          AND (expires_at IS NULL OR expires_at > ?)
        LIMIT 1
        """,
        (user_id, artifact_id, operation, now_iso()),
    ).fetchone()
    return grant is not None


def find_grant_id(
    conn: sqlite3.Connection, user_id: str, artifact_id: str, operation: Operation
) -> str | None:
    """Return the id of the capability grant that would be (or was) used for this access."""
    row = conn.execute(
        """
        SELECT id FROM capability_grants
        WHERE user_id = ?
          AND artifact_id = ?
          AND operation = ?
          AND revoked = 0
          AND (expires_at IS NULL OR expires_at > ?)
        LIMIT 1
        """,
        (user_id, artifact_id, operation, now_iso()),
    ).fetchone()
    return row["id"] if row else None


# ---------------------------------------------------------------------------
# Permission engine — deterministic, no LLM
# ---------------------------------------------------------------------------

def evaluate_access(
    conn: sqlite3.Connection, user_id: str, artifact_id: str, operation: Operation
) -> tuple[Decision, str]:
    """
    Capability-based access check. Allows access only when ALL hold:
    1. User (resolved from a token, never a query param) exists.
    2. Artifact exists.
    3. Artifact status is active or redacted.
    4. User holds a non-revoked, non-expired capability grant for the operation.
    5. Lineage integrity:
       - Non-redacted derived artifact: deny if ANY transitive source is
         revoked or quarantined.
       - Redacted derived artifact: deny only if an INCLUDED parent (one whose
         content was not redacted out) is revoked or quarantined. Redacted-out
         parents are excluded because their content was attested-removed.
    """
    user = conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return "deny", "user_not_found"

    artifact = get_artifact(conn, artifact_id)
    if not artifact:
        return "deny", "artifact_not_found"

    if artifact["status"] == "quarantined":
        return "deny", "derived_from_revoked_source"
    if artifact["status"] not in ("active", "redacted"):
        return "deny", f"artifact_status_{artifact['status']}"

    if not has_grant(conn, user_id, artifact_id, operation):
        return "deny", "missing_capability_grant"

    if artifact["type"] == "derived":
        if artifact["status"] == "redacted":
            # Only included parents can taint a redacted artifact.
            for edge in get_direct_edges(conn, artifact_id):
                if edge["inclusion"] != "included":
                    continue
                parent = get_artifact(conn, edge["parent_artifact_id"])
                if parent and parent["status"] in ("revoked", "quarantined"):
                    return "deny", "derived_from_revoked_source"
        else:
            for parent in get_transitive_parents(conn, artifact_id):
                if parent["status"] in ("revoked", "quarantined"):
                    return "deny", "derived_from_revoked_source"

    return "allow", "capability_and_lineage_valid"


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

def log_audit(
    conn: sqlite3.Connection,
    user_id: str,
    artifact_id: str,
    operation: str,
    decision: Decision,
    reason: str,
    latency_ms: float,
    request_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_events
            (id, timestamp, user_id, artifact_id, operation, decision, reason,
             latency_ms, request_id, detail)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            now_iso(),
            user_id,
            artifact_id,
            operation,
            decision,
            reason,
            latency_ms,
            request_id or new_request_id(),
            json.dumps(detail) if detail else None,
        ),
    )


def can_access(
    user_id: str,
    artifact_id: str,
    operation: Operation,
    request_id: str | None = None,
    purpose: str = "unspecified",
) -> dict[str, Any]:
    rid = request_id or new_request_id()
    start = time.perf_counter()
    with connect() as conn:
        decision, reason = evaluate_access(conn, user_id, artifact_id, operation)
        latency_ms = round((time.perf_counter() - start) * 1000, 3)

        # Structured provenance detail — logged on every access event.
        # Does not influence the decision; purely for audit trail quality.
        detail: dict[str, Any] = {
            "request_id": rid,
            "purpose": purpose,
            "principal": user_id,
            "operation": operation,
        }
        if decision == "allow":
            grant_id = find_grant_id(conn, user_id, artifact_id, operation)
            if grant_id:
                detail["grant_id"] = grant_id
        artifact_row = get_artifact(conn, artifact_id)
        if artifact_row and artifact_row["type"] == "derived":
            detail["lineage_checked"] = True
            detail["lineage_decision"] = "passed" if decision == "allow" else reason

        log_audit(conn, user_id, artifact_id, operation, decision, reason, latency_ms, rid, detail)
        return {"decision": decision, "reason": reason, "latency_ms": latency_ms, "request_id": rid}


# ---------------------------------------------------------------------------
# Response shaping
# ---------------------------------------------------------------------------

def artifact_public(row: sqlite3.Row) -> dict[str, Any]:
    data = row_to_dict(row) or {}
    data.pop("encrypted_content", None)
    return data


def artifact_with_content(row: sqlite3.Row) -> dict[str, Any]:
    data = artifact_public(row)
    data["plaintext_content"] = decrypt(row["encrypted_content"])
    return data


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "biovault"}


# ---------------------------------------------------------------------------
# Scenario seed helpers
# ---------------------------------------------------------------------------

def _seed_biotech(conn: sqlite3.Connection) -> tuple[int, int, dict[str, str]]:
    """Seed the biotech / pharma R&D scenario (default demo).

    BVK-14 kinase program: AI science agents derive a Phase II readiness memo from
    source documents including an adverse-event memo. External CRO is denied the
    derived memo; revoking the adverse-event source quarantines downstream artifacts.
    """
    users = [
        ("u_ceo", "Avery Chen", "CEO", "Leadership"),
        ("u_research", "Maya Patel", "Research Scientist", "R&D"),
        ("u_compchem", "Leo Morgan", "Computational Chemist", "R&D"),
        ("u_regulatory", "Nora Singh", "Regulatory Lead", "Regulatory"),
        ("u_cro", "Owen Brooks", "External CRO Scientist", "Partner"),
        ("u_intern", "Iris Lopez", "Intern", "R&D"),
    ]
    artifacts = [
        ("public_target_paper", "Open Target Biology Paper", "source",
         "Published literature summary for kinase target BVK-14. No patient or "
         "sponsor-confidential data. Available to all team members.", "public"),
        ("internal_sar_table", "Internal SAR Table", "source",
         "Lead series SAR table: BV-101 IC50 18 nM, BV-117 IC50 9 nM. "
         "Solubility flags noted for three scaffolds. Restricted — do not share externally.", "restricted"),
        ("docking_report", "Docking Report", "source",
         "Computational docking predicts hinge-binding pose for BV-117 with "
         "favorable selectivity pocket occupancy. Prepared by Computational Chemistry.", "internal"),
        ("toxicity_report", "GLP Toxicity Report", "source",
         "Rat tox study: reversible ALT elevation at high dose; no observed adverse "
         "effect level under review. Requires regulatory sign-off before Phase II IND.", "restricted"),
        ("cro_assay_report", "CRO Assay Report", "source",
         "Partner CRO assay batch CRO-77 confirms BV-117 potency in duplicate "
         "biochemical screens. Delivered under CDA — external scientists may view.", "internal"),
        ("adverse_event_memo", "Adverse Event Memo", "source",
         "CONFIDENTIAL — sentinel animal event observed in satellite cohort. "
         "Requires executive and regulatory review before Phase II initiation. "
         "Do not distribute without explicit authorisation.", "confidential"),
        ("board_update", "Board Update", "source",
         "Board-facing portfolio update with financing runway, partnership status, "
         "and sensitive development risks. Prepared for Q2 board meeting.", "confidential"),
        ("phase2_readiness_memo", "Phase II Readiness Memo", "derived",
         "DERIVED — synthesises target biology, SAR findings, GLP toxicity signals, "
         "and adverse-event context. Recommendation: gated Phase II preparation "
         "pending safety mitigation.", "confidential"),
    ]

    tokens: dict[str, str] = {}
    for user_id, name, role, team in users:
        tokens[user_id] = add_user(conn, user_id, name, role, team)
    for a in artifacts:
        add_artifact(conn, a[0], a[1], a[2], a[3], a[4], "u_ceo")

    for parent_id in ["public_target_paper", "internal_sar_table", "toxicity_report", "adverse_event_memo"]:
        parent = get_artifact(conn, parent_id)
        conn.execute(
            """
            INSERT INTO lineage_edges
                (parent_artifact_id, child_artifact_id, dependency_type, inclusion,
                 source_hash, created_by, reason)
            VALUES (?, ?, 'source', 'included', ?, 'u_ceo', 'seed_lineage')
            """,
            (parent_id, "phase2_readiness_memo", content_hash(decrypt(parent["encrypted_content"]))),
        )

    all_ids = [a[0] for a in artifacts]
    grant_many(conn, "u_ceo", all_ids, ["read", "derive", "revoke", "grant", "redact"])
    grant_many(conn, "u_regulatory",
               ["toxicity_report", "adverse_event_memo", "phase2_readiness_memo"], ["read"])
    grant_many(conn, "u_research",
               ["public_target_paper", "internal_sar_table", "docking_report", "toxicity_report"],
               ["read", "derive"])
    grant_many(conn, "u_compchem",
               ["public_target_paper", "internal_sar_table", "docking_report"], ["read", "derive"])
    grant_many(conn, "u_cro", ["public_target_paper", "cro_assay_report"], ["read"])
    grant_many(conn, "u_intern", ["public_target_paper"], ["read"])

    return len(users), len(artifacts), tokens


@app.post("/seed")
def seed() -> dict[str, Any]:
    """Reset all tables and load the BVK-14 biotech demo dataset.

    Returns plaintext principal tokens ONCE (demo only). Only hashes are stored.
    """
    init_db()
    with connect() as conn:
        conn.executescript(
            """
            DELETE FROM redaction_attestations;
            DELETE FROM audit_events;
            DELETE FROM lineage_edges;
            DELETE FROM capability_grants;
            DELETE FROM artifacts;
            DELETE FROM users;
            """
        )
        user_count, artifact_count, tokens = _seed_biotech(conn)

    return {
        "status": "seeded",
        "scenario": "biotech",
        "users": user_count,
        "artifacts": artifact_count,
        "tokens": tokens,
        "note": "Plaintext principal tokens are returned only here for demo use. Only hashes are stored.",
    }


@app.get("/users")
def list_users() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT id, name, role, team FROM users ORDER BY team, role")
        return [dict(r) for r in rows]


@app.get("/artifacts")
def list_artifacts() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM artifacts ORDER BY created_at, title").fetchall()
        return [artifact_public(row) for row in rows]


@app.get("/artifacts/{artifact_id}")
def read_artifact(
    artifact_id: str, principal_id: str = Depends(resolve_principal)
) -> dict[str, Any]:
    # Identity comes from the token (principal_id), never a query param.
    result = can_access(principal_id, artifact_id, "read", purpose="artifact_read")
    with connect() as conn:
        row = get_artifact(conn, artifact_id)
        if not row:
            raise HTTPException(status_code=404, detail=result)
        payload: dict[str, Any] = {"access": result, "principal_id": principal_id, "artifact": artifact_public(row)}
        if result["decision"] == "allow":
            payload["artifact"] = artifact_with_content(row)
        return payload


@app.post("/artifacts/{artifact_id}/grant")
def grant_artifact(
    artifact_id: str, request: GrantRequest, issuer_id: str = Depends(resolve_principal)
) -> dict[str, Any]:
    """Grant a capability. Issuer must hold grant/delegate authority on the artifact."""
    rid = new_request_id()
    with connect() as conn:
        if not get_artifact(conn, artifact_id):
            raise HTTPException(status_code=404, detail="artifact_not_found")

    # Issuer must hold a 'grant' capability on this artifact (delegate authority).
    issuer_check = can_access(issuer_id, artifact_id, "grant", rid)
    if issuer_check["decision"] == "deny":
        issuer_check["reason"] = "issuer_lacks_grant_authority"
        with connect() as conn:
            log_audit(
                conn, issuer_id, artifact_id, "grant", "deny",
                "issuer_lacks_grant_authority", 0.0, rid,
                {"issuer": issuer_id, "subject": request.subject_user_id,
                 "scope": request.operation, "purpose": request.purpose},
            )
        return {"access": issuer_check, "granted": False, "grant_id": None}

    with connect() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE id = ?", (request.subject_user_id,)).fetchone():
            raise HTTPException(status_code=404, detail="subject_not_found")
        grant_id = add_grant(conn, request.subject_user_id, artifact_id, request.operation, request.expires_at)
        log_audit(
            conn, issuer_id, artifact_id, "grant", "allow", "capability_granted", 0.0, rid,
            {"grant_id": grant_id, "issuer": issuer_id, "subject": request.subject_user_id,
             "scope": request.operation, "purpose": request.purpose},
        )
        return {
            "access": issuer_check,
            "granted": True,
            "grant_id": grant_id,
            "grant": {
                "grant_id": grant_id,
                "issuer": issuer_id,
                "subject": request.subject_user_id,
                "scope": request.operation,
                "purpose": request.purpose,
                "expires_at": request.expires_at,
                "request_id": rid,
            },
        }


@app.post("/artifacts/{artifact_id}/revoke")
def revoke_artifact(
    artifact_id: str, request: RevokeRequest, principal_id: str = Depends(resolve_principal)
) -> dict[str, Any]:
    rid = new_request_id()
    result = can_access(principal_id, artifact_id, "revoke", rid)
    if result["decision"] == "deny":
        return {"access": result, "revoked": False, "quarantined": []}

    with connect() as conn:
        source = get_artifact(conn, artifact_id)
        if not source:
            raise HTTPException(status_code=404, detail="artifact_not_found")

        conn.execute("UPDATE artifacts SET status = 'revoked' WHERE id = ?", (artifact_id,))
        conn.execute("UPDATE capability_grants SET revoked = 1 WHERE artifact_id = ?", (artifact_id,))
        log_audit(conn, principal_id, artifact_id, "revoke", "allow", "source_revoked", 0.0, rid,
                  {"purpose": request.purpose})

        quarantined: list[str] = []
        for child in get_transitive_children(conn, artifact_id):
            if child["type"] == "derived" and child["status"] == "active":
                conn.execute("UPDATE artifacts SET status = 'quarantined' WHERE id = ?", (child["id"],))
                log_audit(conn, principal_id, child["id"], "read", "deny",
                          "derived_from_revoked_source", 0.0, rid,
                          {"propagated_from": artifact_id})
                quarantined.append(child["id"])

        return {"access": result, "revoked": True, "artifact_id": artifact_id, "quarantined": quarantined}


class QueryRequest(BaseModel):
    artifact_id: str
    purpose: str = "agent_retrieval"
    context: str = ""


@app.post("/query")
def query_artifact(
    request: QueryRequest, principal_id: str = Depends(resolve_principal)
) -> dict[str, Any]:
    """
    Agent-facing retrieval gate for open-weight model runtimes.

    An agent calls this endpoint BEFORE passing content to any model. If the
    decision is 'allow', plaintext_content is returned and the agent may use it
    as context for generation. If the decision is 'deny', no content is returned
    and the model must not attempt to retrieve it through any other path.

    The permission check is identical to GET /artifacts/{id}: same
    resolve_principal(), same evaluate_access(), same log_audit(). No model
    call occurs here. The open-weight model sits entirely outside this boundary.

    Compatible runtimes: Qwen, Llama, Mistral, GLM, and any model using a tool
    or function-calling interface. See docs/ARCHITECTURE.md for the integration
    pattern.
    """
    rid = new_request_id()
    result = can_access(principal_id, request.artifact_id, "read", rid, purpose=request.purpose)

    response: dict[str, Any] = {
        "decision": result["decision"],
        "reason": result["reason"],
        "latency_ms": result["latency_ms"],
        "request_id": rid,
        "artifact_id": request.artifact_id,
        "principal_id": principal_id,
    }

    if result["decision"] == "allow":
        with connect() as conn:
            row = get_artifact(conn, request.artifact_id)
        if row:
            response["title"] = row["title"]
            response["sensitivity"] = row["sensitivity"]
            response["status"] = row["status"]
            response["plaintext_content"] = decrypt(row["encrypted_content"])

    return response


@app.post("/derive")
def derive_artifact(
    request: DeriveRequest, principal_id: str = Depends(resolve_principal)
) -> dict[str, Any]:
    rid = new_request_id()
    with connect() as conn:
        missing = [pid for pid in request.parent_artifact_ids if not get_artifact(conn, pid)]
        if missing:
            raise HTTPException(status_code=404, detail={"missing_parents": missing})

    op: Operation = "redact" if request.redacted else "derive"

    # Patch 2: redaction must not bypass parent permissions or launder revoked sources.
    if request.redacted:
        with connect() as conn:
            revoked_parents = [
                pid for pid in request.parent_artifact_ids
                if (p := get_artifact(conn, pid)) and p["status"] in ("revoked", "quarantined")
            ]
        if revoked_parents:
            with connect() as conn:
                log_audit(conn, principal_id, ",".join(request.parent_artifact_ids), "redact", "deny",
                          "cannot_redact_revoked_source", 0.0, rid, {"revoked_parents": revoked_parents})
            return {"created": False, "reason": "cannot_redact_revoked_source",
                    "revoked_parents": revoked_parents, "parent_checks": []}

    # Authority over EVERY parent for the requested operation.
    parent_checks = [
        {"artifact_id": pid, "access": can_access(principal_id, pid, op, rid)}
        for pid in request.parent_artifact_ids
    ]
    if any(c["access"]["decision"] == "deny" for c in parent_checks):
        reason = "missing_redact_authority" if request.redacted else "missing_derive_authority"
        return {"created": False, "reason": reason, "parent_checks": parent_checks}

    artifact_id = "redacted_phase2_readiness_memo" if request.redacted else f"derived_{uuid.uuid4().hex[:8]}"
    content = (
        "REDACTED — Derived Phase II memo: target biology, SAR findings, and toxicity signals "
        "remain reviewable. Confidential adverse-event content was excluded under a governed "
        "redaction attestation. Safe for broader distribution within approved channels."
        if request.redacted
        else f"Derived memo synthesised from: {', '.join(request.parent_artifact_ids)}."
    )

    with connect() as conn:
        conn.execute("DELETE FROM lineage_edges WHERE child_artifact_id = ?", (artifact_id,))
        conn.execute("DELETE FROM redaction_attestations WHERE artifact_id = ?", (artifact_id,))
        conn.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))

        add_artifact(conn, artifact_id, request.title, "derived", content, "confidential",
                     principal_id, "redacted" if request.redacted else "active")

        included: list[str] = []
        redacted_out: list[str] = []
        for pid in request.parent_artifact_ids:
            parent = get_artifact(conn, pid)
            inclusion = "redacted" if (request.redacted and pid in request.redact_parent_ids) else "included"
            (redacted_out if inclusion == "redacted" else included).append(pid)
            conn.execute(
                """
                INSERT INTO lineage_edges
                    (parent_artifact_id, child_artifact_id, dependency_type, inclusion,
                     source_hash, created_by, reason)
                VALUES (?, ?, 'source', ?, ?, ?, ?)
                """,
                (pid, artifact_id, inclusion, content_hash(decrypt(parent["encrypted_content"])),
                 principal_id, request.reason),
            )

        attestation_id = None
        if request.redacted:
            attestation_id = f"att_{uuid.uuid4().hex[:12]}"
            detail = {
                "included": included,
                "redacted": redacted_out,
                "reason": request.reason,
                "request_id": rid,
                "source_hashes": {
                    pid: content_hash(decrypt(get_artifact(conn, pid)["encrypted_content"]))
                    for pid in request.parent_artifact_ids
                },
            }
            conn.execute(
                """
                INSERT INTO redaction_attestations (id, artifact_id, created_by, reason, created_at, detail)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (attestation_id, artifact_id, principal_id, request.reason, now_iso(), json.dumps(detail)),
            )

        grant_many(conn, principal_id, [artifact_id], ["read", "derive", "revoke", "grant", "redact"])
        if request.redacted:
            grant_many(conn, "u_regulatory", [artifact_id], ["read"])
            if principal_id != "u_ceo":
                grant_many(conn, "u_ceo", [artifact_id], ["read", "derive", "revoke", "grant", "redact"])

        log_audit(conn, principal_id, artifact_id, op, "allow",
                  "redacted_artifact_created" if request.redacted else "derived_artifact_created",
                  0.0, rid, {"attestation_id": attestation_id, "included": included, "redacted": redacted_out})

        return {
            "created": True,
            "artifact": artifact_public(get_artifact(conn, artifact_id)),
            "attestation_id": attestation_id,
            "parent_checks": parent_checks,
        }


@app.get("/lineage/{artifact_id}")
def lineage(artifact_id: str) -> dict[str, Any]:
    with connect() as conn:
        artifact = get_artifact(conn, artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="artifact_not_found")

        # Parents with edge metadata (inclusion / source hash / reason).
        parent_edges = conn.execute(
            """
            SELECT a.*, e.inclusion, e.dependency_type, e.source_hash, e.reason AS edge_reason
            FROM artifacts a
            JOIN lineage_edges e ON e.parent_artifact_id = a.id
            WHERE e.child_artifact_id = ?
            ORDER BY a.title
            """,
            (artifact_id,),
        ).fetchall()
        parents = []
        for row in parent_edges:
            data = artifact_public(row)
            data.pop("inclusion", None)
            parents.append({
                "artifact": {k: data[k] for k in data if k not in ("edge_reason",)},
                "inclusion": row["inclusion"],
                "dependency_type": row["dependency_type"],
                "source_hash": row["source_hash"],
                "reason": row["edge_reason"],
            })

        children = conn.execute(
            """
            SELECT a.* FROM artifacts a
            JOIN lineage_edges e ON e.child_artifact_id = a.id
            WHERE e.parent_artifact_id = ?
            ORDER BY a.title
            """,
            (artifact_id,),
        ).fetchall()

        attestation = conn.execute(
            "SELECT * FROM redaction_attestations WHERE artifact_id = ?", (artifact_id,)
        ).fetchone()

        return {
            "artifact": artifact_public(artifact),
            "parents": parents,
            "children": [artifact_public(r) for r in children],
            "ancestors": [artifact_public(r) for r in get_transitive_parents(conn, artifact_id)],
            "descendants": [artifact_public(r) for r in get_transitive_children(conn, artifact_id)],
            "redaction_attestation": row_to_dict(attestation),
        }


@app.get("/audit")
def audit(limit: int = Query(default=200, le=500)) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# SikaRoute Market — Kaspa-ready agent spending policy (no live Kaspa)
# ---------------------------------------------------------------------------

@app.get("/sika-route/market/scenarios")
def sika_route_list_scenarios() -> dict[str, Any]:
    """List demo market-round scenarios for the spending-policy hook."""
    return {"service": "sika-route", "scenarios": list_demo_scenarios()}


@app.post("/sika-route/market/scenarios/{scenario_id}/run")
def sika_route_run_scenario(scenario_id: str) -> dict[str, Any]:
    """Run a preset demo market round and return agent_spending_policy + policy_hash."""
    try:
        result = run_demo_scenario(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="scenario_not_found") from exc
    print(f"{KASPA_POLICY_HASH_LABEL}: {result['policy_hash']}")
    return result


@app.post("/sika-route/market/round")
def sika_route_market_round(round_input: MarketRoundInput) -> dict[str, Any]:
    """Run one SikaRoute market round; every round emits agent_spending_policy."""
    result = run_market_round(round_input)
    print(f"{KASPA_POLICY_HASH_LABEL}: {result['policy_hash']}")
    return result


@app.get("/sika-route/market/demo-rounds")
def sika_route_demo_rounds() -> dict[str, Any]:
    """Run all built-in demo market rounds (policy hook smoke test)."""
    rounds = run_all_demo_rounds()
    for item in rounds:
        print(f"{KASPA_POLICY_HASH_LABEL}: {item['policy_hash']}")
    return {"service": "sika-route", "rounds": rounds}


@app.get("/metrics/permission-latency")
def permission_latency_metrics() -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT latency_ms, decision FROM audit_events ORDER BY timestamp DESC LIMIT 1000"
        ).fetchall()

    if not rows:
        return {"count": 0, "message": "No audit events recorded yet."}

    latencies = [r["latency_ms"] for r in rows]
    allow_count = sum(1 for r in rows if r["decision"] == "allow")
    p_vals = quantiles(latencies, n=100) if len(latencies) >= 2 else [latencies[0]] * 100

    return {
        "count": len(latencies),
        "allow_count": allow_count,
        "deny_count": len(rows) - allow_count,
        "mean_ms": round(mean(latencies), 3),
        "median_ms": round(median(latencies), 3),
        "p95_ms": round(p_vals[94], 3),
        "p99_ms": round(p_vals[98], 3),
        "min_ms": round(min(latencies), 3),
        "max_ms": round(max(latencies), 3),
    }
