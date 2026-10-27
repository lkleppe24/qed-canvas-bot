"""Sanity check: confirms your Canvas token works and shows what the bot will watch.

Run:  python check_canvas.py
Needs only CANVAS_BASE_URL and CANVAS_TOKEN in .env (no Discord setup required).
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

from canvas import CanvasClient, CanvasError
from tracker import is_group_assignment, is_submitted

load_dotenv()


async def main() -> None:
    base, token = os.getenv("CANVAS_BASE_URL", "").strip(), os.getenv("CANVAS_TOKEN", "").strip()
    if not base or not token:
        sys.exit("Set CANVAS_BASE_URL and CANVAS_TOKEN in .env first.")
    course_ids = [c.strip() for c in os.getenv("COURSE_IDS", "").split(",") if c.strip()]
    try:
        async with CanvasClient(base, token) as canvas:
            courses = await canvas.active_courses()
            print(f"✅ Token works. {len(courses)} active course(s) on your account.")
            if course_ids:
                found = {str(c["id"]) for c in courses}
                for missing in [i for i in course_ids if i not in found]:
                    print(f"⚠️  COURSE_IDS has {missing}, but that isn't one of your active courses. "
                          "Check for a typo.")
                courses = [c for c in courses if str(c["id"]) in course_ids]
                print(f"Showing the {len(courses)} course(s) in COURSE_IDS:\n")
            else:
                print("COURSE_IDS is blank, so the bot will watch all of them:\n")
            for c in courses:
                if c.get("access_restricted_by_date"):
                    continue
                print(f"[{c['id']}] {c.get('name')}")
                assignments = await canvas.assignments_with_submission(c["id"])
                groups = [a for a in assignments if is_group_assignment(a)]
                if not groups:
                    print("    (no group assignments)")
                for a in groups:
                    mark = "✔ submitted" if is_submitted(a.get("submission")) else "… not yet"
                    print(f"    {mark:12} {a.get('name')}")
                print()
    except CanvasError as e:
        sys.exit(f"❌ {e}")
    if not course_ids:
        print("Tip: put the course IDs you care about in COURSE_IDS to limit what the bot watches.")


if __name__ == "__main__":
    asyncio.run(main())