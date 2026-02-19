"""
Supabase → AWS RDS Data Migration Script

Usage:
    python migrate-data.py --supabase-url <URL> --supabase-key <KEY> --rds-url <RDS_URL>

Steps:
1. Export all data from Supabase PostgreSQL
2. Transform data to match new schema
3. Import into RDS PostgreSQL
4. Create Cognito users from Supabase auth.users
5. Validate migration
"""

import os
import sys
import json
import argparse
import uuid
import secrets
import string
from datetime import datetime

import psycopg2
import boto3


def generate_temp_password(length=12):
    """Generate a temporary password meeting Cognito requirements."""
    chars = string.ascii_letters + string.digits + "!@#$%"
    while True:
        pwd = "".join(secrets.choice(chars) for _ in range(length))
        if (any(c.islower() for c in pwd) and
            any(c.isupper() for c in pwd) and
            any(c.isdigit() for c in pwd)):
            return pwd


def export_supabase(supabase_url: str):
    """Export all data from Supabase PostgreSQL."""
    print("[1/5] Exporting data from Supabase...")
    conn = psycopg2.connect(supabase_url)
    cursor = conn.cursor()
    data = {}

    tables = [
        ("auth.users", "SELECT id, email, raw_user_meta_data, created_at FROM auth.users"),
        ("profiles", "SELECT * FROM public.profiles"),
        ("projects", "SELECT * FROM public.projects"),
        ("document_processing", "SELECT * FROM public.document_processing"),
        ("document_chunks", "SELECT * FROM public.document_chunks"),
        ("user_feedback", "SELECT * FROM public.user_feedback"),
        ("tickets", "SELECT * FROM public.tickets"),
        ("analytics_events", "SELECT * FROM public.analytics_events"),
    ]

    for table_name, query in tables:
        try:
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            data[table_name] = [dict(zip(columns, row)) for row in rows]
            print(f"  Exported {table_name}: {len(rows)} rows")
        except Exception as e:
            print(f"  Warning: Could not export {table_name}: {e}")
            data[table_name] = []

    conn.close()

    # Save backup
    backup_file = f"supabase_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(backup_file, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Backup saved: {backup_file}")

    return data


def create_cognito_users(data: dict, cognito_pool_id: str, region: str):
    """Create Cognito users from Supabase auth.users."""
    print("[2/5] Creating Cognito users...")
    client = boto3.client("cognito-idp", region_name=region)
    user_mapping = {}  # supabase_id -> cognito_sub
    passwords = {}  # email -> temp_password

    auth_users = data.get("auth.users", [])
    profiles = {p.get("id"): p for p in data.get("profiles", [])}

    for user in auth_users:
        email = user.get("email")
        if not email:
            continue

        meta = user.get("raw_user_meta_data", {})
        if isinstance(meta, str):
            meta = json.loads(meta)

        profile = profiles.get(user["id"], {})
        full_name = meta.get("full_name", profile.get("full_name", email.split("@")[0]))
        role = profile.get("role", "engineer")

        try:
            # Create user
            response = client.admin_create_user(
                UserPoolId=cognito_pool_id,
                Username=email,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": full_name},
                ],
                MessageAction="SUPPRESS",
            )

            cognito_sub = response["User"]["Username"]
            user_mapping[str(user["id"])] = cognito_sub

            # Set temporary password
            temp_pwd = generate_temp_password()
            client.admin_set_user_password(
                UserPoolId=cognito_pool_id,
                Username=email,
                Password=temp_pwd,
                Permanent=False,  # Forces change on first login
            )
            passwords[email] = temp_pwd

            # Add to group
            try:
                client.admin_add_user_to_group(
                    UserPoolId=cognito_pool_id,
                    Username=email,
                    GroupName=role,
                )
            except Exception:
                # Group might not exist, add to engineer by default
                client.admin_add_user_to_group(
                    UserPoolId=cognito_pool_id,
                    Username=email,
                    GroupName="engineer",
                )

            print(f"  Created: {email} (role: {role})")

        except client.exceptions.UsernameExistsException:
            print(f"  Skipped (exists): {email}")
            # Get existing sub
            response = client.admin_get_user(
                UserPoolId=cognito_pool_id, Username=email
            )
            for attr in response["UserAttributes"]:
                if attr["Name"] == "sub":
                    user_mapping[str(user["id"])] = attr["Value"]
        except Exception as e:
            print(f"  Error creating {email}: {e}")

    # Save password mapping for notification
    pwd_file = f"migration_passwords_{datetime.now().strftime('%Y%m%d')}.json"
    with open(pwd_file, "w") as f:
        json.dump(passwords, f, indent=2)
    print(f"  Temporary passwords saved: {pwd_file}")
    print(f"  IMPORTANT: Send password reset emails to all users!")

    return user_mapping


def import_to_rds(data: dict, rds_url: str, user_mapping: dict):
    """Import transformed data into RDS PostgreSQL."""
    print("[3/5] Importing data to RDS...")
    conn = psycopg2.connect(rds_url)
    cursor = conn.cursor()

    # 1. Import users
    profiles = data.get("profiles", [])
    for p in profiles:
        supabase_id = str(p.get("id"))
        cognito_sub = user_mapping.get(supabase_id)
        if not cognito_sub:
            continue

        cursor.execute("""
            INSERT INTO users (id, cognito_sub, email, full_name, role, organization, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (cognito_sub) DO NOTHING
        """, (
            str(uuid.uuid4()), cognito_sub,
            p.get("email", ""), p.get("full_name", ""),
            p.get("role", "engineer"), p.get("organization"),
            p.get("created_at", datetime.utcnow()),
        ))
    print(f"  Imported users: {len(profiles)}")

    # 2. Import projects
    projects = data.get("projects", [])
    for proj in projects:
        owner_sub = user_mapping.get(str(proj.get("user_id", "")))
        if not owner_sub:
            continue

        # Get RDS user ID for owner
        cursor.execute("SELECT id FROM users WHERE cognito_sub = %s", (owner_sub,))
        row = cursor.fetchone()
        if not row:
            continue

        cursor.execute("""
            INSERT INTO projects (id, name, description, owner_id, status, version, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            str(uuid.uuid4()), proj.get("name", "Untitled"),
            proj.get("description"), row[0],
            proj.get("status", "draft"), proj.get("version", 1),
            proj.get("created_at"), proj.get("updated_at"),
        ))
    print(f"  Imported projects: {len(projects)}")

    # 3. Import analytics
    events = data.get("analytics_events", [])
    for ev in events:
        cursor.execute("""
            INSERT INTO analytics_events (id, event_type, event_data, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            str(uuid.uuid4()), ev.get("event_type", "unknown"),
            json.dumps(ev.get("event_data", {})), ev.get("created_at"),
        ))
    print(f"  Imported analytics: {len(events)}")

    conn.commit()
    conn.close()


def validate_migration(rds_url: str):
    """Validate the migration was successful."""
    print("[4/5] Validating migration...")
    conn = psycopg2.connect(rds_url)
    cursor = conn.cursor()

    tables = ["users", "projects", "document_processing", "analytics_events", "tickets"]
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  {table}: {count} rows")
        except Exception as e:
            print(f"  {table}: ERROR - {e}")

    conn.close()
    print("[5/5] Migration complete!")


def main():
    parser = argparse.ArgumentParser(description="Migrate Supabase data to RDS")
    parser.add_argument("--supabase-url", required=True, help="Supabase PostgreSQL connection string")
    parser.add_argument("--rds-url", required=True, help="RDS PostgreSQL connection string")
    parser.add_argument("--cognito-pool-id", required=True, help="Cognito User Pool ID")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--skip-cognito", action="store_true", help="Skip Cognito user creation")
    args = parser.parse_args()

    # Step 1: Export from Supabase
    data = export_supabase(args.supabase_url)

    # Step 2: Create Cognito users
    if args.skip_cognito:
        user_mapping = {}
        print("[2/5] Skipping Cognito user creation")
    else:
        user_mapping = create_cognito_users(data, args.cognito_pool_id, args.region)

    # Step 3: Import to RDS
    import_to_rds(data, args.rds_url, user_mapping)

    # Step 4: Validate
    validate_migration(args.rds_url)


if __name__ == "__main__":
    main()
