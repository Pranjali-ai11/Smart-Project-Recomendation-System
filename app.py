import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
import urllib.request
import urllib.error

from flask import Flask, g, has_request_context, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "eduforge.db"
HTML_PAGES = {
    "dashboard.html",
    "feed.html",
    "forgot-password.html",
    "index.html",
    "profile.html",
    "recommendations.html",
    "signup.html",
    "submit-project.html",
    "teammates.html",
    "view-idea.html",
}

STATIC_FILES = {"script.js", "styles.css"}
DEFAULT_PASSWORD = "Password@123"
CANONICAL_SKILL_ALIASES = {
    "Python": ["python", "pandas"],
    "Machine Learning": ["machine learning", "ml", "scikit-learn", "tensorflow", "model training"],
    "Data Analysis": ["data analysis", "analytics", "analysis", "data insights"],
    "HTML": ["html", "frontend", "front end", "ui"],
    "CSS": ["css", "styling", "responsive design"],
    "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript", "ts"],
    "React": ["react"],
    "Node.js": ["node.js", "nodejs", "node", "express"],
    "Flask": ["flask", "backend api", "backend", "server-side"],
    "SQLite": ["sqlite"],
    "SQL": ["sql", "database", "db", "queries"],
    "REST APIs": ["rest api", "rest apis", "api", "apis"],
    "Docker": ["docker", "container", "containers"],
    "Figma": ["figma"],
    "Wireframing": ["wireframe", "wireframing"],
    "UX Design": ["ux", "user experience", "usability"],
    "Product Design": ["product design", "design system", "design systems", "prototyping", "prototype"],
    "Research": ["research", "survey", "interview", "benchmark"],
    "Recommendation Systems": ["recommendation", "recommender", "matching engine", "personalization"],
    "Computer Vision": ["computer vision", "vision", "image recognition"],
    "NLP": ["nlp", "natural language", "language model", "text analysis"],
    "Authentication": ["auth", "authentication", "login", "secure access"],
    "Privacy Thinking": ["privacy", "security", "compliance"],
    "Rapid Prototyping": ["rapid prototyping", "prototype", "mvp", "hackathon"],
    "Pitching": ["pitch", "pitching", "presentation"],
    "Team Coordination": ["team coordination", "collaboration", "workflow"],
    "Problem Solving": ["problem solving"],
    "Product Strategy": ["roadmapping", "product strategy", "go-to-market"],
}

DOMAIN_DEFAULT_SKILLS = {
    "AI": ["Python", "Machine Learning", "Data Analysis"],
    "Education": ["Research", "UX Design", "Product Design"],
    "Healthcare": ["Research", "Privacy Thinking", "Data Analysis"],
    "Hackathon": ["Rapid Prototyping", "Pitching", "Team Coordination"],
    "Web Development": ["HTML", "CSS", "JavaScript", "REST APIs"],
}

def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "eduforge-dev-secret")

    @app.before_request
    def before_request() -> None:
        init_db()

    @app.teardown_appcontext
    def close_db(_: Any) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.route("/")
    def home():
        return send_from_directory(BASE_DIR, "index.html")

    @app.route("/api/signup", methods=["POST"])
    def signup():
        payload = request.get_json(silent=True) or {}
        full_name = clean_text(payload.get("full_name"))
        email = clean_text(payload.get("email")).lower()
        password = payload.get("password", "")
        college = clean_text(payload.get("college"))
        year_role = clean_text(payload.get("year_role"))
        goals = clean_text(payload.get("goals"))
        interest_tags = normalize_list(payload.get("interest_tags", []))

        if not full_name or not email or not password:
            return json_error("Full name, email, and password are required.", 400)

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return json_error("An account with this email already exists.", 409)

        now = utc_now()
        cursor = db.execute(
            """
            INSERT INTO users (
                full_name, email, password_hash, college, year_role, goals,
                interested_domains, skills_have, skills_learn, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '[]', ?, ?)
            """,
            (
                full_name,
                email,
                generate_password_hash(password),
                college,
                year_role,
                goals,
                json.dumps(interest_tags),
                now,
                now,
            ),
        )
        db.commit()
        session["user_id"] = cursor.lastrowid
        return jsonify({"ok": True, "user": get_current_user_payload()})

    @app.route("/api/login", methods=["POST"])
    def login():
        payload = request.get_json(silent=True) or {}
        email = clean_text(payload.get("email")).lower()
        password = payload.get("password", "")

        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            return json_error("Invalid email or password.", 401)

        session["user_id"] = user["id"]
        return jsonify({"ok": True, "user": serialize_user(user)})

    @app.route("/api/forgot-password", methods=["POST"])
    def forgot_password():
        payload = request.get_json(silent=True) or {}
        email = clean_text(payload.get("email")).lower()
        new_password = payload.get("new_password", "")

        if not email or not new_password:
            return json_error("Email and new password are required.", 400)
        if not is_valid_password(new_password):
            return json_error(
                "Password must be at least 8 characters and include uppercase, lowercase, number, and special character.",
                400,
            )

        db = get_db()
        user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            return json_error("No account was found with that email.", 404)

        db.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (generate_password_hash(new_password), utc_now(), user["id"]),
        )
        db.commit()
        return jsonify({"ok": True, "message": "Password reset successful. You can log in with your new password."})

    @app.route("/api/logout", methods=["POST"])
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.route("/api/me")
    def me():
        user = require_user()
        if isinstance(user, tuple):
            return user
        return jsonify({"ok": True, "user": serialize_user(user)})

    @app.route("/api/profile", methods=["GET", "PUT", "DELETE"])
    def profile():
        user = require_user()
        if isinstance(user, tuple):
            return user

        if request.method == "GET":
            return jsonify({"ok": True, "profile": serialize_user(user)})

        if request.method == "DELETE":
            delete_user_profile(user["id"])
            session.clear()
            return jsonify({"ok": True})

        payload = request.get_json(silent=True) or {}
        updated = {
            "full_name": clean_text(payload.get("full_name")),
            "college": clean_text(payload.get("college")),
            "year_role": clean_text(payload.get("year_role")),
            "bio": clean_text(payload.get("bio")),
            "experience_level": clean_text(payload.get("experience_level")),
            "availability": clean_text(payload.get("availability")),
            "interested_domains": json.dumps(normalize_list(payload.get("interested_domains", []))),
            "skills_have": json.dumps(normalize_list(payload.get("skills_have", []))),
            "skills_learn": json.dumps(normalize_list(payload.get("skills_learn", []))),
            "github_url": clean_text(payload.get("github_url")),
            "linkedin_url": clean_text(payload.get("linkedin_url")),
            "goals": clean_text(payload.get("goals")),
            "updated_at": utc_now(),
        }
        get_db().execute(
            """
            UPDATE users
            SET full_name = ?, college = ?, year_role = ?, bio = ?, experience_level = ?,
                availability = ?, interested_domains = ?, skills_have = ?, skills_learn = ?,
                github_url = ?, linkedin_url = ?, goals = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                updated["full_name"] or user["full_name"],
                updated["college"],
                updated["year_role"],
                updated["bio"],
                updated["experience_level"],
                updated["availability"],
                updated["interested_domains"],
                updated["skills_have"],
                updated["skills_learn"],
                updated["github_url"],
                updated["linkedin_url"],
                updated["goals"],
                updated["updated_at"],
                user["id"],
            ),
        )
        get_db().commit()
        refreshed = get_user_by_id(user["id"])
        return jsonify({"ok": True, "profile": serialize_user(refreshed)})

    @app.route("/api/dashboard")
    def dashboard():
        user = require_user()
        if isinstance(user, tuple):
            return user

        trending_projects = ensure_trending_projects(compact=True)
        collaborator_matches = suggest_collaborators(user_id=user["id"], limit=3)
        refresh_meta = get_trending_refresh_metadata(db=get_db())
        stats = {
            "related_projects": get_db().execute("SELECT COUNT(*) AS total FROM projects").fetchone()["total"],
            "matching_students": len(collaborator_matches),
            "weekly_trending_refresh": refresh_meta["last_refresh_label"],
            "weekly_trending_next_refresh": refresh_meta["next_refresh_label"],
        }
        spotlight = trending_projects[0] if trending_projects else None
        return jsonify(
            {
                "ok": True,
                "user": serialize_user(user),
                "trending_projects": trending_projects,
                "suggested_collaborators": collaborator_matches,
                "stats": stats,
                "spotlight": spotlight,
            }
        )

    @app.route("/api/projects", methods=["GET", "POST"])
    def projects():
        user = require_user()
        if isinstance(user, tuple):
            return user

        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            project_input = build_project_input(payload)
            validation_error = validate_project_input(project_input)
            if validation_error:
                return json_error(validation_error, 400)

            duplicate = find_duplicate_project(project_input)
            if duplicate:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "duplicate": True,
                            "message": "A very similar project already exists, so this one was not stored.",
                            "project": duplicate,
                        }
                    ),
                    409,
                )

            insights = generate_project_insights(project_input, user)
            now = utc_now()
            db = get_db()
            cursor = db.execute(
                """
                INSERT INTO projects (
                    user_id, title, description, domain, status, tech_stack, tags, github_url,
                    demo_url, objective, target_users, problem_statement, key_features,
                    required_skills, innovation_score, creator_skill_gap, creator_skill_gap_summary,
                    team_size, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    project_input["title"],
                    project_input["description"],
                    project_input["domain"],
                    project_input["status"],
                    json.dumps(project_input["tech_stack"]),
                    json.dumps(project_input["tags"]),
                    project_input["github_url"],
                    project_input["demo_url"],
                    project_input["objective"],
                    project_input["target_users"],
                    project_input["problem_statement"],
                    json.dumps(project_input["key_features"]),
                    json.dumps(insights["required_skills"]),
                    insights["innovation_score"],
                    json.dumps(insights["creator_skill_gap"]),
                    insights["creator_skill_gap_summary"],
                    project_input["team_size"],
                    now,
                    now,
                ),
            )
            project_id = cursor.lastrowid
            db.execute(
                "INSERT INTO project_team_members (project_id, user_id, joined_at) VALUES (?, ?, ?)",
                (project_id, user["id"], now),
            )
            db.commit()
            return jsonify({"ok": True, "project": get_project_payload(project_id, user["id"], increment_view=False)})

        search = clean_text(request.args.get("search"))
        domain = clean_text(request.args.get("domain"))
        project_rows = query_projects(search=search, domain=domain)
        items = [serialize_project(row, viewer_id=user["id"], increment_view=False) for row in project_rows]
        return jsonify({"ok": True, "projects": items})

    @app.route("/api/projects/<int:project_id>", methods=["GET", "PUT", "DELETE"])
    def project_detail(project_id: int):
        user = require_user()
        if isinstance(user, tuple):
            return user

        project = get_project_by_id(project_id)
        if not project:
            return json_error("Project not found.", 404)

        if request.method == "GET":
            payload = get_project_payload(project_id, user["id"], increment_view=True)
            ensure_trending_projects()
            return jsonify({"ok": True, "project": payload})

        if project["user_id"] != user["id"]:
            return json_error("Only the project owner can manage this project.", 403)

        if request.method == "DELETE":
            delete_project(project_id)
            return jsonify({"ok": True})

        payload = request.get_json(silent=True) or {}
        project_input = build_project_input(payload)
        validation_error = validate_project_input(project_input)
        if validation_error:
            return json_error(validation_error, 400)
        current_team_size = len(get_team_members(project_id))
        if project_input["team_size"] < current_team_size:
            return json_error(
                f"Team size cannot be smaller than the current member count ({current_team_size}).",
                400,
            )

        duplicate = find_duplicate_project(project_input, exclude_project_id=project_id)
        if duplicate:
            return (
                jsonify(
                    {
                        "ok": False,
                        "duplicate": True,
                        "message": "A very similar project already exists, so this update was not saved.",
                        "project": duplicate,
                    }
                ),
                409,
            )

        insights = generate_project_insights(project_input, user)
        get_db().execute(
            """
            UPDATE projects
            SET title = ?, description = ?, domain = ?, status = ?, tech_stack = ?, tags = ?,
                github_url = ?, demo_url = ?, objective = ?, target_users = ?, problem_statement = ?,
                key_features = ?, required_skills = ?, innovation_score = ?, creator_skill_gap = ?,
                team_size = ?,
                creator_skill_gap_summary = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                project_input["title"],
                project_input["description"],
                project_input["domain"],
                project_input["status"],
                json.dumps(project_input["tech_stack"]),
                json.dumps(project_input["tags"]),
                project_input["github_url"],
                project_input["demo_url"],
                project_input["objective"],
                project_input["target_users"],
                project_input["problem_statement"],
                json.dumps(project_input["key_features"]),
                json.dumps(insights["required_skills"]),
                insights["innovation_score"],
                json.dumps(insights["creator_skill_gap"]),
                project_input["team_size"],
                insights["creator_skill_gap_summary"],
                utc_now(),
                project_id,
            ),
        )
        get_db().commit()
        return jsonify({"ok": True, "project": get_project_payload(project_id, user["id"], increment_view=False)})

    @app.route("/api/projects/<int:project_id>/join-request", methods=["POST"])
    def project_join_request(project_id: int):
        user = require_user()
        if isinstance(user, tuple):
            return user

        project = get_project_by_id(project_id)
        if not project:
            return json_error("Project not found.", 404)

        if project["user_id"] == user["id"]:
            return json_error("Project owners are already on their own team.", 409)

        members = get_team_members(project_id)
        if any(member["id"] == user["id"] for member in members):
            return json_error("You are already on this team.", 409)
        if len(members) >= safe_int(project["team_size"], 2):
            return json_error(f"This project team is already full at {safe_int(project['team_size'], 2)} members.", 409)

        existing_request = get_pending_join_request(project_id, user["id"])
        if existing_request:
            return json_error("Your join request is already pending owner approval.", 409)

        now = utc_now()
        get_db().execute(
            """
            INSERT INTO project_join_requests (project_id, requester_id, owner_id, status, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (project_id, user["id"], project["user_id"], now, now),
        )
        get_db().commit()
        return jsonify({"ok": True})

    @app.route("/api/projects/<int:project_id>/like", methods=["POST"])
    def toggle_project_like(project_id: int):
        user = require_user()
        if isinstance(user, tuple):
            return user

        project = get_project_by_id(project_id)
        if not project:
            return json_error("Project not found.", 404)

        liked = is_project_liked_by_viewer(project_id, user["id"])
        if liked:
            get_db().execute(
                "DELETE FROM project_likes WHERE project_id = ? AND user_id = ?",
                (project_id, user["id"]),
            )
        else:
            get_db().execute(
                "INSERT INTO project_likes (project_id, user_id, created_at) VALUES (?, ?, ?)",
                (project_id, user["id"], utc_now()),
            )
        get_db().commit()
        return jsonify({"ok": True, "liked": not liked, "likes": get_project_like_count(project_id)})

    @app.route("/api/projects/<int:project_id>/join-requests")
    def list_project_join_requests(project_id: int):
        user = require_user()
        if isinstance(user, tuple):
            return user

        project = get_project_by_id(project_id)
        if not project:
            return json_error("Project not found.", 404)
        if project["user_id"] != user["id"]:
            return json_error("Only the project owner can view join requests.", 403)

        return jsonify({"ok": True, "requests": get_project_join_requests(project_id)})

    @app.route("/api/projects/<int:project_id>/join-requests/<int:request_id>", methods=["POST"])
    def handle_project_join_request(project_id: int, request_id: int):
        user = require_user()
        if isinstance(user, tuple):
            return user

        project = get_project_by_id(project_id)
        if not project:
            return json_error("Project not found.", 404)
        if project["user_id"] != user["id"]:
            return json_error("Only the project owner can manage join requests.", 403)

        payload = request.get_json(silent=True) or {}
        action = clean_text(payload.get("action")).lower()
        if action not in {"approve", "decline"}:
            return json_error("Action must be approve or decline.", 400)

        join_request = get_project_join_request_by_id(request_id)
        if not join_request or join_request["project_id"] != project_id:
            return json_error("Join request not found.", 404)
        if join_request["status"] != "pending":
            return json_error("That join request has already been handled.", 409)

        if action == "approve":
            members = get_team_members(project_id)
            if len(members) >= safe_int(project["team_size"], 2):
                return json_error(f"This project team is already full at {safe_int(project['team_size'], 2)} members.", 409)
            get_db().execute(
                "INSERT INTO project_team_members (project_id, user_id, joined_at) VALUES (?, ?, ?)",
                (project_id, join_request["requester_id"], utc_now()),
            )

        get_db().execute(
            "UPDATE project_join_requests SET status = ?, updated_at = ? WHERE id = ?",
            ("approved" if action == "approve" else "declined", utc_now(), request_id),
        )
        get_db().commit()
        return jsonify(
            {
                "ok": True,
                "team": get_team_members(project_id),
                "requests": get_project_join_requests(project_id),
            }
        )

    @app.route("/api/trending-projects")
    def trending_projects():
        user = require_user()
        if isinstance(user, tuple):
            return user
        return jsonify({"ok": True, "projects": ensure_trending_projects(compact=True)})

    @app.route("/api/collaborators")
    def collaborators():
        user = require_user()
        if isinstance(user, tuple):
            return user

        search = clean_text(request.args.get("search"))
        domain = clean_text(request.args.get("domain"))
        project_id = request.args.get("project_id")
        items = suggest_collaborators(
            user_id=user["id"],
            project_id=int(project_id) if project_id else None,
            search=search,
            domain=domain,
        )
        return jsonify({"ok": True, "collaborators": items})

    @app.route("/api/accept-connection", methods=["POST"])
    def accept_connection():

        user = require_user()
        if isinstance(user, tuple):
            return user

        payload = request.get_json(silent=True) or {}
        requester_id = int(payload.get("requester_id"))

        db = get_db()

        now = utc_now()

        db.execute(
            """
            UPDATE connection_requests
            SET status = 'accepted',
                updated_at = ?
            WHERE requester_id = ?
            AND target_user_id = ?
            """,
            (now, requester_id, user["id"]),
        )

        db.commit()

        return jsonify({
            "ok": True,
            "message": "Connection accepted"
        })
    
    @app.route("/api/reject-connection", methods=["POST"])
    def reject_connection():

        user = require_user()
        if isinstance(user, tuple):
            return user

        payload = request.get_json(silent=True) or {}
        requester_id = int(payload.get("requester_id"))

        db = get_db()

        db.execute(
            """
            DELETE FROM connection_requests
            WHERE requester_id = ?
            AND target_user_id = ?
            """,
            (requester_id, user["id"]),
        )

        db.commit()

        return jsonify({
            "ok": True,
            "message": "Connection rejected"
        })
    
    @app.route("/api/remove-connection", methods=["POST"])
    def remove_connection():
        try:
            user = require_user()
            if isinstance(user, tuple):
                return user

            data = request.get_json(silent=True) or {}
            other_user_id = data.get("user_id")

            if not other_user_id:
                return jsonify({
                    "ok": False,
                    "message": "User id required"
                }), 400

            db = get_db()

            print("Current user:", user["id"])
            print("Other user:", other_user_id)
            try:
                cursor = db.execute(
                    """
                    DELETE FROM connection_requests
                    WHERE
                    (
                        requester_id = ?
                        AND target_user_id = ?
                    )
                    OR
                    (
                        requester_id = ?
                        AND target_user_id = ?
                    )
                    """,
                    (
                        user["id"],
                        other_user_id,
                        other_user_id,
                        user["id"]
                    )
                )
                deleted = cursor.rowcount
                print("Deleted rows (connection_requests):", deleted)

            except Exception as e:
                print("connection_requests failed:", e)
                cursor = db.execute(
                    """
                    DELETE FROM connections
                    WHERE
                    (
                        user_id = ?
                        AND connection_id = ?
                    )
                    OR
                    (
                        user_id = ?
                        AND connection_id = ?
                    )
                    """,
                    (
                        user["id"],
                        other_user_id,
                        other_user_id,
                        user["id"]
                    )
                )
                deleted = cursor.rowcount
                print("Deleted rows (connections):", deleted)

            db.commit()

            if deleted == 0:
                return jsonify({
                    "ok": False,
                    "message": "No connection found to remove"
                }), 404

            return jsonify({
                "ok": True,
                "message": "Connection removed successfully"
            })

        except Exception as e:
            print("REMOVE CONNECTION ERROR:", e)

            return jsonify({
                "ok": False,
                "message": "Failed to remove connection"
            }), 500
        
    @app.route("/api/connections", methods=["POST"])
    def send_connection():

        user = require_user()
        if isinstance(user, tuple):
            return user

        data = request.get_json(silent=True) or {}

        target_user_id = data.get("target_user_id")

        if not target_user_id:
            return jsonify({
                "ok": False,
                "message": "Missing target_user_id"
            }), 400

        if target_user_id == user["id"]:
            return jsonify({
                "ok": False,
                "message": "You cannot connect with yourself."
            }), 409

        db = get_db()

        now = utc_now()

        existing = db.execute(
            """
            SELECT requester_id, target_user_id, status
            FROM connection_requests
            WHERE (requester_id = ? AND target_user_id = ?)
               OR (requester_id = ? AND target_user_id = ?)
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user["id"], target_user_id, target_user_id, user["id"])
        ).fetchone()

        if existing:
            if existing["status"] == "accepted":
                return jsonify({
                    "ok": False,
                    "message": "You are already connected."
                }), 409
            if existing["status"] == "pending" and existing["requester_id"] == user["id"]:
                return jsonify({
                    "ok": False,
                    "message": "Connection request already sent."
                }), 409
            if existing["status"] == "pending" and existing["requester_id"] == target_user_id:
                return jsonify({
                    "ok": False,
                    "message": "This user has already sent you a connection request. Check your pending requests."
                }), 409
            return jsonify({
                "ok": False,
                "message": "A connection record already exists for this user."
            }), 409

        db.execute(
            """
            INSERT INTO connection_requests
            (requester_id, target_user_id, status, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, ?)
            """,
            (user["id"], target_user_id, now, now)
        )

        db.commit()

        return jsonify({
            "ok": True,
            "message": "Connection request sent"
        })

    @app.route("/api/connections", methods=["GET"])
    def get_connections():
        user = require_user()
        if isinstance(user, tuple):
            return user

        db = get_db()

        rows = db.execute(
            """
            SELECT u.*
            FROM users u
            JOIN connection_requests c
            ON (
                (u.id = c.requester_id AND c.target_user_id = ?)
                OR
                (u.id = c.target_user_id AND c.requester_id = ?)
            )
            WHERE c.status = 'accepted'
            """,
            (user["id"], user["id"]),
        ).fetchall()
        return jsonify({
            "ok": True,
            "connections": [serialize_user(r) for r in rows]
        })
    @app.route("/api/pending-requests")
    def pending_requests():

        user = require_user()
        if isinstance(user, tuple):
            return user

        db = get_db()

        rows = db.execute(
            """
            SELECT u.*
            FROM users u
            JOIN connection_requests c
            ON u.id = c.requester_id
            WHERE
            c.target_user_id = ?
            AND c.status = 'pending'
            """,
            (user["id"],),
        ).fetchall()

        return jsonify({
            "ok": True,
            "requests": [serialize_user(r) for r in rows]
        })

    @app.route("/api/recommendations")
    def recommendations():
        user = require_user()
        if isinstance(user, tuple):
            return user

        domain = clean_text(request.args.get("domain")) or "All"
        search = clean_text(request.args.get("search"))
        recommendations_payload = get_ollama_recommendations(user, domain, search)
        return jsonify({"ok": True, "recommendations": recommendations_payload})

    @app.route("/<path:filename>")
    def static_pages(filename: str):
        if filename in HTML_PAGES or filename in STATIC_FILES:
            return send_from_directory(BASE_DIR, filename)
        return jsonify({"ok": False, "message": "Not found."}), 404

    with app.app_context():
        init_db()

    return app

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            college TEXT,
            year_role TEXT,
            bio TEXT,
            experience_level TEXT,
            availability TEXT,
            interested_domains TEXT NOT NULL DEFAULT '[]',
            skills_have TEXT NOT NULL DEFAULT '[]',
            skills_learn TEXT NOT NULL DEFAULT '[]',
            github_url TEXT,
            linkedin_url TEXT,
            goals TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            domain TEXT NOT NULL,
            status TEXT NOT NULL,
            team_size INTEGER NOT NULL DEFAULT 2,
            tech_stack TEXT NOT NULL DEFAULT '[]',
            tags TEXT NOT NULL DEFAULT '[]',
            github_url TEXT,
            demo_url TEXT,
            objective TEXT,
            target_users TEXT,
            problem_statement TEXT,
            key_features TEXT NOT NULL DEFAULT '[]',
            required_skills TEXT NOT NULL DEFAULT '[]',
            innovation_score INTEGER NOT NULL DEFAULT 0,
            creator_skill_gap TEXT NOT NULL DEFAULT '[]',
            creator_skill_gap_summary TEXT,
            views INTEGER NOT NULL DEFAULT 0,
            trending_score REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(title, domain),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS project_team_members (
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (project_id, user_id),
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS project_join_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            requester_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, requester_id),
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (requester_id) REFERENCES users (id),
            FOREIGN KEY (owner_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS connection_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_id INTEGER NOT NULL,
            target_user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(requester_id, target_user_id),
            FOREIGN KEY (requester_id) REFERENCES users (id),
            FOREIGN KEY (target_user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS project_likes (
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (project_id, user_id),
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS app_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    added_team_size_column = ensure_projects_team_size_column(db)
    normalize_project_team_sizes(db, fill_from_current_members=added_team_size_column)
    seed_database_if_needed(db)
    db.commit()

def seed_database_if_needed(db: sqlite3.Connection) -> None:
    user_count = db.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
    if user_count:
        return

    now = utc_now()
    users = [
        {
            "full_name": "Nidhi Verma",
            "email": "nidhi@campus.edu",
            "college": "ABC Institute of Technology",
            "year_role": "3rd Year, Computer Science",
            "bio": "Education-focused builder who enjoys recommendation systems and campus collaboration products.",
            "experience_level": "Intermediate",
            "availability": "Evenings + weekends",
            "interested_domains": ["AI", "Education", "Web Development"],
            "skills_have": ["HTML", "CSS", "JavaScript", "Python", "Flask"],
            "skills_learn": ["SQLite", "Recommendation Systems", "Product Design"],
            "goals": "Build student-first products with strong recommendation and collaboration features.",
        },
        {
            "full_name": "Aarav Mehta",
            "email": "aarav@campus.edu",
            "college": "National Institute of Technology",
            "year_role": "Frontend Developer",
            "bio": "Builds polished interfaces for student tools and hackathon prototypes.",
            "experience_level": "Intermediate",
            "availability": "Evenings + weekends",
            "interested_domains": ["Web Development", "Hackathon", "Education"],
            "skills_have": ["HTML", "CSS", "JavaScript", "React", "Figma"],
            "skills_learn": ["Flask", "Backend APIs"],
            "goals": "Join product-minded student teams that care about usability.",
        },
        {
            "full_name": "Riya Sharma",
            "email": "riya@campus.edu",
            "college": "Delhi Technical University",
            "year_role": "UI/UX Designer",
            "bio": "Turns product ideas into smooth flows, wireframes, and memorable visual systems.",
            "experience_level": "Intermediate",
            "availability": "Weekends",
            "interested_domains": ["Education", "Healthcare", "Hackathon"],
            "skills_have": ["Figma", "Wireframing", "Prototyping", "Design Systems"],
            "skills_learn": ["Frontend Development"],
            "goals": "Collaborate on products that feel useful and thoughtful from day one.",
        },
        {
            "full_name": "Kabir Verma",
            "email": "kabir@campus.edu",
            "college": "VIT Chennai",
            "year_role": "Backend Developer",
            "bio": "Enjoys APIs, data models, authentication systems, and scalable student platforms.",
            "experience_level": "Advanced",
            "availability": "Flexible",
            "interested_domains": ["AI", "Web Development", "Cloud"],
            "skills_have": ["Python", "Flask", "SQLite", "REST APIs", "Docker"],
            "skills_learn": ["Machine Learning"],
            "goals": "Build dependable backends for ambitious student products.",
        },
        {
            "full_name": "Sneha Iyer",
            "email": "sneha@campus.edu",
            "college": "SRM Institute of Science and Technology",
            "year_role": "Machine Learning Enthusiast",
            "bio": "Works on analytics, ML experiments, recommendation signals, and data-backed product ideas.",
            "experience_level": "Intermediate",
            "availability": "Evenings",
            "interested_domains": ["AI", "Healthcare", "Education"],
            "skills_have": ["Python", "Pandas", "Scikit-learn", "TensorFlow"],
            "skills_learn": ["MLOps", "Product Analytics"],
            "goals": "Collaborate on ML-backed student products with measurable impact.",
        },
        {
            "full_name": "Zoya Khan",
            "email": "zoya@campus.edu",
            "college": "Mumbai University",
            "year_role": "Product Strategist",
            "bio": "Helps teams shape scope, define features, and present ideas clearly.",
            "experience_level": "Intermediate",
            "availability": "Flexible",
            "interested_domains": ["Education", "Healthcare", "Community"],
            "skills_have": ["Research", "Roadmapping", "Pitching", "Team Coordination"],
            "skills_learn": ["SQL", "Growth Analytics"],
            "goals": "Support technical builders with strong product strategy and storytelling.",
        },
    ]

    for user in users:
        db.execute(
            """
            INSERT INTO users (
                full_name, email, password_hash, college, year_role, bio, experience_level,
                availability, interested_domains, skills_have, skills_learn, goals, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["full_name"],
                user["email"],
                generate_password_hash(DEFAULT_PASSWORD),
                user["college"],
                user["year_role"],
                user["bio"],
                user["experience_level"],
                user["availability"],
                json.dumps(user["interested_domains"]),
                json.dumps(user["skills_have"]),
                json.dumps(user["skills_learn"]),
                user["goals"],
                now,
                now,
            ),
        )

    user_rows = db.execute("SELECT * FROM users").fetchall()
    user_map = {row["email"]: row for row in user_rows}
    sample_projects = [
        {
            "email": "riya@campus.edu",
            "title": "Campus Mentor Lens",
            "description": "A mentor discovery platform helping students find seniors and alumni by interest clusters and career goals.",
            "domain": "Education",
            "status": "In Progress",
            "team_size": 4,
            "tech_stack": ["Flask", "SQLite", "JavaScript", "Figma"],
            "tags": ["mentorship", "education", "network"],
            "github_url": "https://github.com/example/campus-mentor-lens",
            "demo_url": "https://example.com/campus-mentor-lens",
            "objective": "Improve how students discover mentors across campus and alumni circles.",
            "target_users": "College students looking for guidance, mentors, and alumni connections.",
            "problem_statement": "Students often struggle to find the right mentors because information is fragmented and informal.",
            "key_features": ["Mentor discovery", "Interest filters", "Goal-based matching"],
        },
        {
            "email": "kabir@campus.edu",
            "title": "HackSprint Team Matchboard",
            "description": "A team formation board that matches students using skills, goals, and hackathon interests.",
            "domain": "Hackathon",
            "status": "Idea",
            "team_size": 5,
            "tech_stack": ["Python", "Flask", "SQLite", "JavaScript"],
            "tags": ["hackathon", "matching", "students"],
            "github_url": "https://github.com/example/hacksprint-matchboard",
            "demo_url": "https://example.com/hacksprint-matchboard",
            "objective": "Help students form balanced hackathon teams quickly.",
            "target_users": "Students preparing for hackathons and weekend builds.",
            "problem_statement": "Students rarely have a fast, structured way to find teammates with complementary skills.",
            "key_features": ["Skill graph", "Availability matching", "Domain filters"],
        },
        {
            "email": "sneha@campus.edu",
            "title": "GreenRoute Hostel Optimizer",
            "description": "An analytics tool that predicts energy waste and recommends sustainable actions for student hostels.",
            "domain": "AI",
            "status": "In Progress",
            "team_size": 3,
            "tech_stack": ["Python", "Pandas", "Scikit-learn", "Flask"],
            "tags": ["ai", "sustainability", "campus"],
            "github_url": "https://github.com/example/greenroute-hostel-optimizer",
            "demo_url": "https://example.com/greenroute-hostel-optimizer",
            "objective": "Reduce hostel energy waste through predictive insights.",
            "target_users": "Hostel managers, campus sustainability teams, and students.",
            "problem_statement": "Campus sustainability efforts often lack proactive insights into waste patterns.",
            "key_features": ["Usage forecasting", "Waste alerts", "Campus dashboard"],
        },
        {
            "email": "zoya@campus.edu",
            "title": "HealthBridge Student Companion",
            "description": "A wellbeing portal for students with support resources, mental health guidance, and appointment pathways.",
            "domain": "Healthcare",
            "status": "Completed",
            "team_size": 2,
            "tech_stack": ["Flask", "SQLite", "HTML", "CSS"],
            "tags": ["healthcare", "student-support", "community"],
            "github_url": "https://github.com/example/healthbridge-student-companion",
            "demo_url": "https://example.com/healthbridge-student-companion",
            "objective": "Make student wellbeing support easier to discover and use.",
            "target_users": "Students seeking wellbeing resources and appointment support.",
            "problem_statement": "Students often do not know where or how to access campus wellbeing resources.",
            "key_features": ["Resource library", "Support pathways", "Appointment guidance"],
        },
    ]

    for project in sample_projects:
        creator = user_map[project["email"]]
        try:
            insights = generate_project_insights(project, creator)
        except Exception as e:

            print("Seed insight error:", e)

        insights = {
            "required_skills": [],
            "innovation_score": estimate_innovation_score(project),
            "creator_skill_gap": [],
            "creator_skill_gap_summary": ""
        }
        project_input = {
                            "title": project["title"],
                            "description": project["description"],
                            "domain": project["domain"],
                            "tags": project.get("tags", [])
                        }

        duplicate = find_duplicate_project(project_input)

        if duplicate:
            raise ValueError(f"Duplicate project found: {project['title']}")
        cursor = db.execute(
            """
            INSERT INTO projects (
                user_id, title, description, domain, status, tech_stack, tags, github_url,
                demo_url, objective, target_users, problem_statement, key_features,
                required_skills, innovation_score, creator_skill_gap, creator_skill_gap_summary,
                views, team_size, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                creator["id"],
                project["title"],
                project["description"],
                project["domain"],
                project["status"],
                json.dumps(project["tech_stack"]),
                json.dumps(project["tags"]),
                project["github_url"],
                project["demo_url"],
                project["objective"],
                project["target_users"],
                project["problem_statement"],
                json.dumps(project["key_features"]),
                json.dumps(insights["required_skills"]),
                insights["innovation_score"],
                json.dumps(insights["creator_skill_gap"]),
                insights["creator_skill_gap_summary"],
                0,
                project["team_size"],
                now,
                now,
            ),
        )
        project_id = cursor.lastrowid
        db.execute(
            "INSERT INTO project_team_members (project_id, user_id, joined_at) VALUES (?, ?, ?)",
            (project_id, creator["id"], now),
        )

    team_assignments = [
        ("Campus Mentor Lens", "nidhi@campus.edu"),
        ("Campus Mentor Lens", "aarav@campus.edu"),
        ("HackSprint Team Matchboard", "nidhi@campus.edu"),
        ("HackSprint Team Matchboard", "zoya@campus.edu"),
        ("GreenRoute Hostel Optimizer", "kabir@campus.edu"),
        ("HealthBridge Student Companion", "riya@campus.edu"),
    ]
    project_rows = db.execute("SELECT id, title FROM projects").fetchall()
    project_map = {row["title"]: row["id"] for row in project_rows}
    for project_title, email in team_assignments:
     if project_title not in project_map:
        continue   

    db.execute(
        "INSERT INTO project_team_members (project_id, user_id, joined_at) VALUES (?, ?, ?)",
        (project_map[project_title], user_map[email]["id"], now),
    );

    set_meta("trending_last_refreshed", now, db=db)
    ensure_trending_projects(force=True, db=db)

def require_user():
    user_id = session.get("user_id")
    if not user_id:
        return json_error("Please log in first.", 401)
    user = get_user_by_id(user_id)
    if not user:
        session.clear()
        return json_error("Please log in again.", 401)
    return user

def get_user_by_id(user_id: int):
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

def get_project_by_id(project_id: int):
    return get_db().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

def build_project_input(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": clean_text(payload.get("title")),
        "description": clean_text(payload.get("description")),
        "domain": clean_text(payload.get("domain")),
        "status": clean_text(payload.get("status")) or "Idea",
        "team_size": parse_team_size(payload.get("team_size")),
        "tech_stack": normalize_list(payload.get("tech_stack", [])),
        "tags": normalize_list(payload.get("tags", [])),
        "github_url": clean_text(payload.get("github_url")),
        "demo_url": clean_text(payload.get("demo_url")),
        "objective": clean_text(payload.get("objective")),
        "target_users": clean_text(payload.get("target_users")),
        "problem_statement": clean_text(payload.get("problem_statement")),
        "key_features": normalize_list(payload.get("key_features", [])),
    }

def validate_project_input(project: dict[str, Any]) -> str | None:
    required = {
        "title": "Project title is required.",
        "description": "Project description is required.",
        "domain": "Project domain is required.",
        "team_size": "Team size is required.",
        "github_url": "GitHub link is required.",
        "demo_url": "Demo link is required.",
        "objective": "Project objective is required.",
        "target_users": "Target users are required.",
        "problem_statement": "Problem statement is required.",
    }
    for key, message in required.items():
        if not project.get(key):
            return message
    if not isinstance(project["team_size"], int):
        return "Invalid team size."
    if project["team_size"] < 2 or project["team_size"] > 5:
        return "Team size must be between 2 and 5 members."
    if not project["tech_stack"]:
        return "Add at least one tech stack item."
    if not project["tags"]:
        return "Add at least one project tag."
    if not project["key_features"]:
        return "Add at least one key feature."
    return None

def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()

def normalize_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [part.strip() for part in values.split(",")]
    normalized = []
    seen = set()
    for value in values:
        cleaned = clean_text(value)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            normalized.append(cleaned)
    return normalized

def canonicalize_skill(value: Any) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""

    normalized = cleaned.lower()
    for canonical, aliases in CANONICAL_SKILL_ALIASES.items():
        if normalized == canonical.lower() or normalized in aliases:
            return canonical
        if any(alias in normalized for alias in aliases):
            return canonical

    return cleaned

def normalize_skill_list(values: Any) -> list[str]:
    return normalize_list([canonicalize_skill(value) for value in normalize_list(values)])

def merge_skill_lists(*skill_groups: Any, limit: int = 8) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in skill_groups:
        for skill in normalize_skill_list(group):
            key = skill.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(skill)
            if len(merged) >= limit:
                return merged
    return merged

def compute_missing_skills(required_skills: Any, current_skills: Any) -> list[str]:
    required = normalize_skill_list(required_skills)
    current = {skill.lower() for skill in normalize_skill_list(current_skills)}
    return [skill for skill in required if skill.lower() not in current]

def extract_skill_signals_from_project(project: dict[str, Any]) -> list[str]:
    combined_text = " ".join(
        [
            clean_text(project.get("title")),
            clean_text(project.get("description")),
            clean_text(project.get("domain")),
            clean_text(project.get("objective")),
            clean_text(project.get("target_users")),
            clean_text(project.get("problem_statement")),
            " ".join(normalize_list(project.get("tech_stack", []))),
            " ".join(normalize_list(project.get("tags", []))),
            " ".join(normalize_list(project.get("key_features", []))),
        ]
    ).lower()

    inferred: list[str] = []
    for canonical, aliases in CANONICAL_SKILL_ALIASES.items():
        if canonical.lower() in combined_text or any(alias in combined_text for alias in aliases):
            inferred.append(canonical)

    return normalize_skill_list(inferred)

def parse_team_size(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def is_valid_password(password: str) -> bool:
    return bool(re.fullmatch(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}", password or ""))

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def json_error(message: str, status: int):
    return jsonify({"ok": False, "message": message}), status

def parse_json_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return normalize_list(raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return normalize_list(raw.split(","))
    return normalize_list(data)

def serialize_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "college": row["college"] or "",
        "year_role": row["year_role"] or "",
        "bio": row["bio"] or "",
        "experience_level": row["experience_level"] or "",
        "availability": row["availability"] or "",
        "interested_domains": parse_json_list(row["interested_domains"]),
        "skills_have": parse_json_list(row["skills_have"]),
        "skills_learn": parse_json_list(row["skills_learn"]),
        "github_url": row["github_url"] or "",
        "linkedin_url": row["linkedin_url"] or "",
        "goals": row["goals"] or "",
    }

def get_current_user_payload() -> dict[str, Any] | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = get_user_by_id(user_id)
    return serialize_user(user) if user else None

def query_projects(search: str = "", domain: str = "") -> list[sqlite3.Row]:
    sql = """
        SELECT projects.*, users.full_name AS owner_name
        FROM projects
        JOIN users ON users.id = projects.user_id
        WHERE 1 = 1
    """
    params: list[Any] = []
    if domain and domain.lower() != "all":
        sql += " AND lower(projects.domain) = ?"
        params.append(domain.lower())
    if search:
        needle = f"%{search.lower()}%"
        sql += """
            AND (
                lower(projects.title) LIKE ?
                OR lower(projects.description) LIKE ?
                OR lower(projects.domain) LIKE ?
                OR lower(projects.tags) LIKE ?
            )
        """
        params.extend([needle, needle, needle, needle])
    sql += " ORDER BY projects.created_at DESC"
    return get_db().execute(sql, params).fetchall()

def serialize_project(
    row: sqlite3.Row,
    viewer_id: int | None,
    increment_view: bool = False,
    compact: bool = False,
) -> dict[str, Any]:
    project_id = row["id"]
    if increment_view:
        get_db().execute("UPDATE projects SET views = views + 1 WHERE id = ?", (project_id,))
        get_db().commit()
        row = get_project_by_id(project_id)

    likes = get_project_like_count(project_id)

    if compact:
        return {
            "id": project_id,
            "title": row["title"],
            "description": row["description"],
            "domain": row["domain"],
            "team_size": safe_int(row["team_size"], 2),
            "innovation_score": row["innovation_score"],
            "trending_score": row["trending_score"],
            "views": row["views"],
            "likes": likes,
        }

    owner = get_user_by_id(row["user_id"])
    required_skills = parse_json_list(row["required_skills"])
    creator_skill_gap = parse_json_list(row["creator_skill_gap"])
    team_members = get_team_members(project_id)
    team_size = safe_int(row["team_size"], 2)
    viewer_gap = calculate_viewer_skill_gap(required_skills, viewer_id)
    pending_join_requests = get_project_join_requests(project_id) if viewer_id == row["user_id"] else []
    join_request_status = get_join_request_status(project_id, viewer_id) if viewer_id and viewer_id != row["user_id"] else ""

    return {
        "id": project_id,
        "title": row["title"],
        "description": row["description"],
        "domain": row["domain"],
        "status": row["status"],
        "team_size": team_size,
        "tech_stack": parse_json_list(row["tech_stack"]),
        "tags": parse_json_list(row["tags"]),
        "github_url": row["github_url"] or "",
        "demo_url": row["demo_url"] or "",
        "objective": row["objective"] or "",
        "target_users": row["target_users"] or "",
        "problem_statement": row["problem_statement"] or "",
        "key_features": parse_json_list(row["key_features"]),
        "required_skills": required_skills,
        "innovation_score": row["innovation_score"],
        "creator_skill_gap": creator_skill_gap,
        "creator_skill_gap_summary": row["creator_skill_gap_summary"] or "",
        "viewer_skill_gap": viewer_gap,
        "owner": serialize_user(owner) if owner else None,
        "views": row["views"],
        "likes": likes,
        "liked_by_viewer": is_project_liked_by_viewer(project_id, viewer_id),
        "trending_score": row["trending_score"],
        "team": team_members,
        "team_is_full": len(team_members) >= team_size,
        "is_owner": viewer_id == row["user_id"],
        "join_request_status": join_request_status,
        "pending_join_requests": pending_join_requests,
        "collaborator_suggestions": suggest_collaborators(
            user_id=viewer_id,
            project_id=project_id,
            limit=max(0, team_size - len(team_members)),
        )
        if viewer_id
        else [],
    }

def get_project_payload(project_id: int, viewer_id: int | None, increment_view: bool) -> dict[str, Any] | None:
    row = get_project_by_id(project_id)
    if not row:
        return None
    return serialize_project(row, viewer_id=viewer_id, increment_view=increment_view)

def calculate_viewer_skill_gap(required_skills: list[str], viewer_id: int | None) -> dict[str, Any]:
    normalized_required = normalize_skill_list(required_skills)
    if not viewer_id:
        return {"missing_skills": normalized_required, "summary": "Log in to compare this project against your profile."}

    viewer = get_user_by_id(viewer_id)
    if not viewer:
        return {"missing_skills": normalized_required, "summary": "Viewer profile was not found."}

    viewer_skills = normalize_skill_list(parse_json_list(viewer["skills_have"]))
    fallback_missing = compute_missing_skills(normalized_required, viewer_skills)
    prompt_payload = {
        "viewer_name": viewer["full_name"],
        "viewer_skills": viewer_skills,
        "required_skills": normalized_required,
    }
    ai_result = call_ollama_json(
        (
            "Analyze the gap between a user's current skills and a project's required skills. "
            "Return strict JSON with missing_skills and summary. "
            "missing_skills must be a concise array of skill names."
        ),
        prompt_payload,
    )
    if isinstance(ai_result, dict):
        missing = compute_missing_skills(
            merge_skill_lists(ai_result.get("missing_skills", []), fallback_missing, limit=max(8, len(fallback_missing))),
            viewer_skills,
        )
        summary = build_skill_gap_summary(missing)
        return {"missing_skills": missing, "summary": summary}

    return {"missing_skills": fallback_missing, "summary": build_skill_gap_summary(fallback_missing)}

def find_duplicate_project(project_input: dict[str, Any], exclude_project_id: int | None = None) -> dict[str, Any] | None:
    rows = get_db().execute("SELECT * FROM projects").fetchall()
    best_match = None
    best_score = 0.0

    for row in rows:
        if exclude_project_id and row["id"] == exclude_project_id:
            continue
        existing_domain = clean_text(row["domain"]).lower()
        new_domain = clean_text(project_input["domain"]).lower()
        domain_match = existing_domain == new_domain
        title_ratio = similarity(normalize_text(row["title"]), normalize_text(project_input["title"]))
        description_ratio = similarity(normalize_text(row["description"]), normalize_text(project_input["description"]))
        token_overlap = jaccard_similarity(
            tokenize_project_text(row["title"], row["description"], row["tags"]),
            tokenize_project_text(project_input["title"], project_input["description"], project_input["tags"]),
        )

        duplicate_score = (title_ratio * 0.45) + (description_ratio * 0.35) + (token_overlap * 0.2)
        if domain_match:
            duplicate_score += 0.1

        is_duplicate = domain_match and (
            (title_ratio >= 0.96 and token_overlap >= 0.45)
            or (title_ratio >= 0.9 and description_ratio >= 0.78)
            or duplicate_score >= 0.9
        )

        if is_duplicate and duplicate_score > best_score:
            best_score = duplicate_score
            best_match = serialize_project(row, viewer_id=session.get("user_id"), increment_view=False)

    return best_match

def normalize_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

def similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()

def tokenize_project_text(title: str, description: str, tags: Any) -> set[str]:
    tag_text = " ".join(parse_json_list(tags) if isinstance(tags, str) else normalize_list(tags))
    combined = f"{title} {description} {tag_text}".lower()
    return {token for token in re.findall(r"[a-z0-9]+", combined) if len(token) > 2}

def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)

def generate_project_insights(project: dict[str, Any], user: sqlite3.Row) -> dict[str, Any]:
    deterministic_required_skills = infer_required_skills(project)
    creator_skills = normalize_skill_list(parse_json_list(user["skills_have"]))
    prompt_payload = {
        "project": {
            "title": project["title"],
            "description": project["description"],
            "domain": project["domain"],
            "status": project["status"],
            "tech_stack": project["tech_stack"],
            "tags": project["tags"],
            "objective": project["objective"],
            "target_users": project["target_users"],
            "problem_statement": project["problem_statement"],
            "key_features": project["key_features"],
        },
        "creator": {
            "name": user["full_name"],
            "skills_have": parse_json_list(user["skills_have"]),
            "skills_learn": parse_json_list(user["skills_learn"]),
            "interested_domains": parse_json_list(user["interested_domains"]),
        },
    }
    ai_result = call_ollama_json(
        (
            "Analyze a student project. Return strict JSON with required_skills, innovation_score, "
            "creator_skill_gap, and creator_skill_gap_summary. "
            "innovation_score must be an integer from 0 to 100."
        ),
        prompt_payload,
    )

    if isinstance(ai_result, dict):
        required_skills = merge_skill_lists(
            ai_result.get("required_skills", []),
            deterministic_required_skills,
            limit=8,
        )
        innovation_score = safe_int(ai_result.get("innovation_score"), 65)
        creator_gap = compute_missing_skills(required_skills, creator_skills)
        summary = build_skill_gap_summary(creator_gap)
        return {
            "required_skills": required_skills or deterministic_required_skills,
            "innovation_score": max(0, min(100, innovation_score)),
            "creator_skill_gap": creator_gap,
            "creator_skill_gap_summary": summary,
        }

    required_skills = deterministic_required_skills
    creator_gap = compute_missing_skills(required_skills, creator_skills)
    return {
        "required_skills": required_skills,
        "innovation_score": estimate_innovation_score(project),
        "creator_skill_gap": creator_gap,
        "creator_skill_gap_summary": build_skill_gap_summary(creator_gap),
    }

def infer_required_skills(project: dict[str, Any]) -> list[str]:
    domain_defaults = DOMAIN_DEFAULT_SKILLS.get(project["domain"], ["Problem Solving"])
    return merge_skill_lists(
        project.get("tech_stack", []),
        extract_skill_signals_from_project(project),
        domain_defaults,
        limit=8,
    )

def estimate_innovation_score(project: dict[str, Any]) -> int:
    title = clean_text(project.get("title"))
    description = clean_text(project.get("description"))
    domain = clean_text(project.get("domain"))
    status = clean_text(project.get("status"))
    objective = clean_text(project.get("objective"))
    target_users = clean_text(project.get("target_users"))
    problem_statement = clean_text(project.get("problem_statement"))
    tech_stack = normalize_list(project.get("tech_stack", []))
    tags = normalize_list(project.get("tags", []))
    key_features = normalize_list(project.get("key_features", []))
    github_url = clean_text(project.get("github_url"))
    demo_url = clean_text(project.get("demo_url"))

    combined_text = " ".join(
        [
            title,
            description,
            domain,
            objective,
            target_users,
            problem_statement,
            " ".join(tech_stack),
            " ".join(tags),
            " ".join(key_features),
        ]
    ).lower()

    def score_from_count(count: int, thresholds: list[int]) -> int:
        score = 2
        for threshold in thresholds:
            if count >= threshold:
                score += 2
        return min(score, 10)

    def keyword_hits(keywords: list[str]) -> int:
        return sum(1 for keyword in keywords if keyword in combined_text)

    novelty = score_from_count(len(set(tags + key_features + tech_stack)), [3, 5, 7, 9])
    novelty += min(keyword_hits(["ai", "ml", "iot", "blockchain", "nlp", "vision", "analytics", "automation"]), 2)
    novelty = min(novelty, 10)

    problem_relevance = 2
    if problem_statement:
        problem_relevance += 3
    if target_users:
        problem_relevance += 2
    if objective:
        problem_relevance += 1
    problem_relevance += min(
        keyword_hits(["student", "campus", "education", "health", "sustainability", "career", "community"]),
        2,
    )
    problem_relevance = min(problem_relevance, 10)

    technical_complexity = score_from_count(len(set(tech_stack + key_features)), [2, 4, 6, 8])
    technical_complexity += min(
        keyword_hits(["ai", "machine learning", "flask", "api", "database", "iot", "computer vision", "nlp"]),
        2,
    )
    technical_complexity = min(technical_complexity, 10)

    feasibility = 4
    if objective:
        feasibility += 1
    if target_users:
        feasibility += 1
    if len(key_features) <= 6:
        feasibility += 2
    if github_url or demo_url:
        feasibility += 1
    if status.lower() in {"prototype", "mvp", "active", "in progress"}:
        feasibility += 1
    feasibility = min(feasibility, 10)

    impact = 3
    impact += min(
        keyword_hits(["student", "community", "career", "health", "sustainability", "accessibility", "learning"]),
        4,
    )
    if target_users:
        impact += 1
    if problem_statement:
        impact += 1
    impact = min(impact, 10)

    scalability = 3
    if target_users:
        scalability += 2
    if demo_url or github_url:
        scalability += 1
    scalability += min(keyword_hits(["platform", "dashboard", "assistant", "portal", "system", "multilingual"]), 3)
    scalability = min(scalability, 10)

    category_groups = 0
    if keyword_hits(["ai", "machine learning", "nlp", "vision"]) > 0:
        category_groups += 1
    if keyword_hits(["web", "app", "portal", "dashboard", "flask", "api"]) > 0:
        category_groups += 1
    if keyword_hits(["iot", "sensor", "hardware"]) > 0:
        category_groups += 1
    if keyword_hits(["health", "education", "career", "sustainability", "community"]) > 0:
        category_groups += 1
    interdisciplinary_nature = min(2 + category_groups * 2, 10)

    market_need = 3
    if target_users:
        market_need += 2
    if problem_statement:
        market_need += 2
    market_need += min(keyword_hits(["need", "problem", "challenge", "support", "guidance", "matching"]), 3)
    market_need = min(market_need, 10)

    prototype_progress = 2
    if github_url:
        prototype_progress += 3
    if demo_url:
        prototype_progress += 3
    if status.lower() in {"prototype", "mvp", "active", "completed"}:
        prototype_progress += 2
    prototype_progress = min(prototype_progress, 10)

    research_usage = 2 + min(
        keyword_hits(["research", "survey", "dataset", "analytics", "analysis", "public health", "benchmark"]),
        5,
    )
    research_usage = min(research_usage, 10)

    weighted_score = (
        0.20 * novelty +
        0.15 * problem_relevance +
        0.15 * technical_complexity +
        0.10 * feasibility +
        0.15 * impact +
        0.10 * scalability +
        0.05 * interdisciplinary_nature +
        0.05 * market_need +
        0.03 * prototype_progress +
        0.02 * research_usage
    ) * 10

    return max(0, min(100, round(weighted_score)))

def project_row_to_input(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "title": row["title"],
        "description": row["description"],
        "domain": row["domain"],
        "status": row["status"],
        "team_size": safe_int(row["team_size"], 2),
        "tech_stack": parse_json_list(row["tech_stack"]),
        "tags": parse_json_list(row["tags"]),
        "github_url": row["github_url"] or "",
        "demo_url": row["demo_url"] or "",
        "objective": row["objective"] or "",
        "target_users": row["target_users"] or "",
        "problem_statement": row["problem_statement"] or "",
        "key_features": parse_json_list(row["key_features"]),
    }

def build_skill_gap_summary(missing_skills: list[str]) -> str:
    if not missing_skills:
        return "Current skills already cover the main needs of this project."
    summary = f"Focus on {', '.join(missing_skills[:4])}"
    if len(missing_skills) > 4:
        summary += f", and {len(missing_skills) - 4} more areas"
    summary += " to close the skill gap."
    return summary

def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default

def ensure_projects_team_size_column(db: sqlite3.Connection) -> bool:
    columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(projects)").fetchall()
    }
    if "team_size" in columns:
        return False

    db.execute("ALTER TABLE projects ADD COLUMN team_size INTEGER NOT NULL DEFAULT 2")
    return True

def normalize_project_team_sizes(db: sqlite3.Connection, fill_from_current_members: bool = False) -> None:
    if fill_from_current_members:
        db.execute(
            """
            UPDATE projects
            SET team_size = (
                CASE
                    WHEN (
                        SELECT COUNT(*)
                        FROM project_team_members
                        WHERE project_team_members.project_id = projects.id
                    ) < 2 THEN 2
                    WHEN (
                        SELECT COUNT(*)
                        FROM project_team_members
                        WHERE project_team_members.project_id = projects.id
                    ) > 5 THEN 5
                    ELSE (
                        SELECT COUNT(*)
                        FROM project_team_members
                        WHERE project_team_members.project_id = projects.id
                    )
                END
            )
            """
        )

    db.execute("UPDATE projects SET team_size = 2 WHERE team_size IS NULL OR team_size < 2")
    db.execute("UPDATE projects SET team_size = 5 WHERE team_size > 5")

def get_team_members(project_id: int) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT users.*, project_team_members.joined_at
        FROM project_team_members
        JOIN users ON users.id = project_team_members.user_id
        WHERE project_team_members.project_id = ?
        ORDER BY project_team_members.joined_at ASC
        """,
        (project_id,),
    ).fetchall()
    items = []
    for row in rows:
        user_payload = serialize_user(row)
        user_payload["joined_at"] = row["joined_at"]
        items.append(user_payload)
    return items

def get_project_join_requests(project_id: int) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT project_join_requests.*, users.full_name, users.email, users.college, users.year_role, users.bio
        FROM project_join_requests
        JOIN users ON users.id = project_join_requests.requester_id
        WHERE project_join_requests.project_id = ? AND project_join_requests.status = 'pending'
        ORDER BY project_join_requests.created_at ASC
        """,
        (project_id,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "requester_id": row["requester_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "requester": {
                "id": row["requester_id"],
                "full_name": row["full_name"],
                "email": row["email"],
                "college": row["college"] or "",
                "year_role": row["year_role"] or "",
                "bio": row["bio"] or "",
            },
        }
        for row in rows
    ]

def get_pending_join_request(project_id: int, requester_id: int):
    return get_db().execute(
        """
        SELECT * FROM project_join_requests
        WHERE project_id = ? AND requester_id = ? AND status = 'pending'
        """,
        (project_id, requester_id),
    ).fetchone()

def get_project_join_request_by_id(request_id: int):
    return get_db().execute("SELECT * FROM project_join_requests WHERE id = ?", (request_id,)).fetchone()

def get_join_request_status(project_id: int, requester_id: int | None) -> str:
    if not requester_id:
        return ""
    row = get_db().execute(
        """
        SELECT status FROM project_join_requests
        WHERE project_id = ? AND requester_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (project_id, requester_id),
    ).fetchone()
    return row["status"] if row else ""

def get_project_like_count(project_id: int) -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM project_likes WHERE project_id = ?", (project_id,)).fetchone()
    return row["total"] if row else 0

def is_project_liked_by_viewer(project_id: int, viewer_id: int | None) -> bool:
    if not viewer_id:
        return False
    row = get_db().execute(
        "SELECT 1 FROM project_likes WHERE project_id = ? AND user_id = ?",
        (project_id, viewer_id),
    ).fetchone()
    return bool(row)

def get_connection_status(requester_id: int | None, target_user_id: int) -> str:
    if not requester_id:
        return ""
    row = get_db().execute(
        """
        SELECT requester_id, target_user_id, status
        FROM connection_requests
        WHERE (requester_id = ? AND target_user_id = ?)
           OR (requester_id = ? AND target_user_id = ?)
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (requester_id, target_user_id, target_user_id, requester_id),
    ).fetchone()
    if not row:
        return ""
    if row["status"] == "accepted":
        return "accepted"
    if row["status"] == "pending":
        return "pending" if row["requester_id"] == requester_id else "incoming_pending"
    return row["status"]

def suggest_collaborators(
    user_id: int | None,
    project_id: int | None = None,
    search: str = "",
    domain: str = "",
    limit: int = 6,
) -> list[dict[str, Any]]:
    db = get_db()
    viewer = get_user_by_id(user_id) if user_id else None
    candidates = db.execute("SELECT * FROM users ORDER BY full_name ASC").fetchall()
    project = get_project_by_id(project_id) if project_id else None
    team_ids = {member["id"] for member in get_team_members(project_id)} if project_id else set()

    viewer_domains = {item.lower() for item in parse_json_list(viewer["interested_domains"])} if viewer else set()
    viewer_skills = {item.lower() for item in parse_json_list(viewer["skills_have"])} if viewer else set()
    project_required_skills = {item.lower() for item in parse_json_list(project["required_skills"])} if project else set()
    project_domain = project["domain"].lower() if project else clean_text(domain).lower()
    search_term = search.lower()

    scored = []
    for candidate in candidates:
        if user_id and candidate["id"] == user_id:
            continue
        if candidate["id"] in team_ids:
            continue

        candidate_domains = {item.lower() for item in parse_json_list(candidate["interested_domains"])}
        candidate_skills = {item.lower() for item in parse_json_list(candidate["skills_have"])}
        candidate_blob = " ".join(
            [
                candidate["full_name"] or "",
                candidate["college"] or "",
                candidate["year_role"] or "",
                candidate["bio"] or "",
                " ".join(candidate_domains),
                " ".join(candidate_skills),
            ]
        ).lower()

        if search_term and search_term not in candidate_blob:
            continue
        if project_domain and project_domain != "all" and project_domain not in candidate_domains and project_domain not in candidate_blob:
            continue

        score = 0
        shared_domains = viewer_domains & candidate_domains
        shared_skills = viewer_skills & candidate_skills
        complementary_skills = project_required_skills & candidate_skills
        score += len(shared_domains) * 4
        score += len(shared_skills) * 2
        score += len(complementary_skills) * 5
        if viewer and candidate["availability"] and candidate["availability"] == viewer["availability"]:
            score += 2
        if project_domain and project_domain in candidate_blob:
            score += 3
        if score <= 0 and not search_term and not project_domain:
            score = 1

        reasons = []
        if shared_domains:
            reasons.append(f"Shared domains: {', '.join(sorted(shared_domains))}")
        if complementary_skills:
            reasons.append(f"Project-fit skills: {', '.join(sorted(complementary_skills))}")
        if shared_skills:
            reasons.append(f"Shared skills: {', '.join(sorted(shared_skills))}")
        if not reasons:
            reasons.append("Profile overlaps with your current interests and project themes.")

        scored.append(
            (
                score,
                {
                    **serialize_user(candidate),
                    "match_score": score,
                    "match_reason": reasons[0],
                    "connection_status": get_connection_status(user_id, candidate["id"]),
                },
            )
        )

    scored.sort(key=lambda item: (-item[0], item[1]["full_name"]))
    return [item[1] for item in scored[:limit]]

def ensure_trending_projects(
    force: bool = False,
    db: sqlite3.Connection | None = None,
    compact: bool = False,
) -> list[dict[str, Any]]:
    local_db = db or get_db()
    raw_last_refresh = get_meta("trending_last_refreshed", db=local_db)
    should_refresh = force or not raw_last_refresh
    if raw_last_refresh and not force:
        try:
            last_refresh = datetime.fromisoformat(raw_last_refresh)
            should_refresh = datetime.now(timezone.utc) - last_refresh >= timedelta(days=7)
        except ValueError:
            should_refresh = True

    if should_refresh:
        project_rows = local_db.execute("SELECT * FROM projects").fetchall()
        now = datetime.now(timezone.utc)
        for row in project_rows:
            project_input = project_row_to_input(row)
            innovation_score = estimate_innovation_score(project_input)
            created_at = datetime.fromisoformat(row["created_at"])
            age_days = max((now - created_at).days, 0)
            freshness_boost = max(0, 100 - min(age_days * 4, 100))
            likes = get_project_like_count(row["id"])
            join_requests = local_db.execute(
                "SELECT COUNT(*) AS total FROM project_join_requests WHERE project_id = ? AND status = 'pending'",
                (row["id"],),
            ).fetchone()["total"]
            team_members = local_db.execute(
                "SELECT COUNT(*) AS total FROM project_team_members WHERE project_id = ?",
                (row["id"],),
            ).fetchone()["total"]
            views_score = min(row["views"] * 12, 100)
            likes_score = min(likes * 18, 100)
            join_requests_score = min(join_requests * 25, 100)
            collaboration_score = min(max(team_members - 1, 0) * 18, 100)
            trending_score = (
                0.25 * likes_score +
                0.20 * views_score +
                0.15 * join_requests_score +
                0.10 * collaboration_score +
                0.15 * innovation_score +
                0.15 * freshness_boost
            )
            local_db.execute(
                "UPDATE projects SET innovation_score = ?, trending_score = ?, updated_at = ? WHERE id = ?",
                (innovation_score, trending_score, utc_now(), row["id"]),
            )
        set_meta("trending_last_refreshed", utc_now(), db=local_db)
        local_db.commit()

    rows = local_db.execute(
        """
        SELECT * FROM projects
        ORDER BY trending_score DESC, innovation_score DESC, views DESC
        LIMIT 5
        """
    ).fetchall()
    viewer_id = session.get("user_id") if has_request_context() else None
    return [
        serialize_project(row, viewer_id=viewer_id, increment_view=False, compact=compact)
        for row in rows
    ]

def get_trending_refresh_metadata(db: sqlite3.Connection | None = None) -> dict[str, str]:
    local_db = db or get_db()
    raw_last_refresh = get_meta("trending_last_refreshed", db=local_db)
    if not raw_last_refresh:
        return {
            "last_refresh_label": "Never",
            "next_refresh_label": "On first dashboard refresh",
        }

    try:
        last_refresh = datetime.fromisoformat(raw_last_refresh)
        next_refresh = last_refresh + timedelta(days=7)
        return {
            "last_refresh_label": last_refresh.astimezone().strftime("%d %b %Y, %I:%M %p"),
            "next_refresh_label": next_refresh.astimezone().strftime("%d %b %Y, %I:%M %p"),
        }
    except ValueError:
        return {
            "last_refresh_label": raw_last_refresh,
            "next_refresh_label": "7 days after the next valid refresh",
        }

def get_meta(key: str, db: sqlite3.Connection | None = None) -> str | None:
    local_db = db or get_db()
    row = local_db.execute("SELECT meta_value FROM app_meta WHERE meta_key = ?", (key,)).fetchone()
    return row["meta_value"] if row else None

def set_meta(key: str, value: str, db: sqlite3.Connection | None = None) -> None:
    local_db = db or get_db()
    local_db.execute(
        """
        INSERT INTO app_meta (meta_key, meta_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value, updated_at = excluded.updated_at
        """,
        (key, value, utc_now()),
    )

def delete_project(project_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM project_team_members WHERE project_id = ?", (project_id,))
    db.execute("DELETE FROM project_join_requests WHERE project_id = ?", (project_id,))
    db.execute("DELETE FROM project_likes WHERE project_id = ?", (project_id,))
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    db.commit()

def delete_user_profile(user_id: int) -> None:
    db = get_db()
    owned_projects = db.execute("SELECT id FROM projects WHERE user_id = ?", (user_id,)).fetchall()
    for row in owned_projects:
        delete_project(row["id"])

    db.execute("DELETE FROM project_team_members WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM project_join_requests WHERE requester_id = ? OR owner_id = ?", (user_id, user_id))
    db.execute("DELETE FROM project_likes WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM connection_requests WHERE requester_id = ? OR target_user_id = ?", (user_id, user_id))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()

def get_ollama_recommendations(user: sqlite3.Row, domain: str, search: str = "") -> dict[str, Any]:
    domain_filter = domain if domain.lower() != "all" else ""
    projects = query_projects(search=search, domain=domain_filter)
    local_recommendations = build_local_recommendations(user, projects, domain, search)
    collaborator_matches = suggest_collaborators(
        user_id=user["id"],
        search=search,
        domain=domain_filter,
        limit=4,
    )
    prompt_payload = {
        "domain": domain,
        "search": search,
        "user_name": user["full_name"],
        "user_domains": parse_json_list(user["interested_domains"]),
        "user_skills": parse_json_list(user["skills_have"]),
        "projects": [
            {
                "title": row["title"],
                "domain": row["domain"],
                "description": row["description"],
                "innovation_score": row["innovation_score"],
                "required_skills": parse_json_list(row["required_skills"]),
            }
            for row in projects[:8]
        ],
    }
    ollama_output = call_ollama_json(
        (
            "You are helping recommend student projects. Return strict JSON with keys explanation and items. "
            "items must be an array of objects with title, domain, summary, match_reason, and innovation_score. "
            "Use only the supplied projects when possible."
        ),
        prompt_payload,
    )
    if not ollama_output:
        return {
            "source": "fallback",
            "explanation": "Ollama is not configured or did not return usable JSON, so these recommendations were generated locally from your profile, keyword search, and stored projects.",
            "items": local_recommendations,
            "collaborators": collaborator_matches,
        }

    merged_items = []
    existing_by_title = {item["title"].lower(): item for item in local_recommendations}
    for item in ollama_output.get("items", []):
        title = clean_text(item.get("title"))
        if not title:
            continue
        local_match = existing_by_title.get(title.lower())
        merged_items.append(
            {
                "title": title,
                "domain": clean_text(item.get("domain")) or (local_match["domain"] if local_match else domain),
                "summary": clean_text(item.get("summary")) or (local_match["summary"] if local_match else ""),
                "match_reason": clean_text(item.get("match_reason")) or (local_match["match_reason"] if local_match else ""),
                "innovation_score": int(item.get("innovation_score") or (local_match["innovation_score"] if local_match else 0)),
                "project_id": local_match["project_id"] if local_match else None,
            }
        )

    if not merged_items:
        merged_items = local_recommendations

    return {
        "source": "ollama",
        "explanation": clean_text(ollama_output.get("explanation"))
        or "Recommendations were generated with Ollama using your profile, chosen domain, and stored projects.",
        "items": merged_items[:6],
        "collaborators": collaborator_matches,
    }

def build_local_recommendations(user: sqlite3.Row, projects: list[sqlite3.Row], domain: str, search: str = "") -> list[dict[str, Any]]:
    user_domains = {item.lower() for item in parse_json_list(user["interested_domains"])}
    user_skills = {item.lower() for item in parse_json_list(user["skills_have"])}
    search_terms = {token for token in re.findall(r"[a-z0-9]+", search.lower()) if len(token) > 2}
    ranked = []

    for row in projects:
        project_skills = {item.lower() for item in parse_json_list(row["required_skills"])}
        project_blob = " ".join(
            [
                row["title"] or "",
                row["domain"] or "",
                row["description"] or "",
                row["tags"] or "",
                row["objective"] or "",
                row["problem_statement"] or "",
            ]
        ).lower()
        keyword_hits = sum(1 for token in search_terms if token in project_blob)
        domain_bonus = 10 if domain.lower() == "all" or row["domain"].lower() == domain.lower() else 0
        shared_domain_bonus = 8 if row["domain"].lower() in user_domains else 0
        skill_overlap = len(user_skills & project_skills) * 3
        score = domain_bonus + shared_domain_bonus + skill_overlap + (keyword_hits * 5) + row["innovation_score"]
        reason = []
        if row["domain"].lower() in user_domains:
            reason.append("matches your preferred domain")
        overlap = list(user_skills & project_skills)
        if overlap:
            reason.append(f"aligns with your skills in {', '.join(overlap[:3])}")
        if keyword_hits:
            reason.append(f"matches your keyword search in {keyword_hits} relevant areas")
        if not reason:
            reason.append("fits the domain and current project trends")

        ranked.append(
            (
                score,
                {
                    "project_id": row["id"],
                    "title": row["title"],
                    "domain": row["domain"],
                    "summary": row["description"],
                    "match_reason": ", ".join(reason),
                    "innovation_score": row["innovation_score"],
                },
            )
        )

    ranked.sort(key=lambda item: (-item[0], item[1]["title"]))
    return [item[1] for item in ranked[:6]]

def call_ollama_json(prompt):
    try:
        import json
        import urllib.request

        url = "http://localhost:11434/api/generate"

        data = json.dumps({
            "model": "llama3",
            "prompt": prompt,
            "stream": False
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        response = urllib.request.urlopen(req, timeout=10)

        result = json.loads(
            response.read().decode()
        )

        return result

    except Exception as e:

        print("OLLAMA ERROR:", e)
        return {
            "innovation_score": 50,
            "skill_gap": [],
            "summary": "AI service unavailable — using fallback scoring."
        }

def extract_json_object(raw_text: str) -> dict[str, Any] | None:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(raw_text[start : end + 1])
    except json.JSONDecodeError:
        return None

def call_ollama_json(prompt: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        url = "http://localhost:11434/api/generate"
        prompt_text = clean_text(prompt)
        if payload is not None:
            prompt_text = (
                f"{prompt_text}\n\n"
                "Return only valid JSON.\n"
                f"Input data:\n{json.dumps(payload, ensure_ascii=True)}"
            )

        data = json.dumps(
            {
                "model": "llama3",
                "prompt": prompt_text,
                "stream": False,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        response = urllib.request.urlopen(req, timeout=10)
        result = json.loads(response.read().decode())
        if not isinstance(result, dict):
            return None

        raw_response = result.get("response", "")
        if not isinstance(raw_response, str) or not raw_response.strip():
            return None

        parsed = extract_json_object(raw_response)
        return parsed if isinstance(parsed, dict) else None
    except Exception as e:
        print("OLLAMA ERROR:", e)
        return None

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)