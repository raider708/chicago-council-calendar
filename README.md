# Chicago City Council & Committee Calendar

A subscribable calendar feed of Chicago City Council and committee meetings, built from the
[City Clerk eLMS public API](https://api.chicityclerkelms.chicago.gov/).

**Subscribe URL:** `https://raider708.github.io/chicago-council-calendar/chicago-council.ics`

## How it works

- A GitHub Action runs every hour and pulls meetings from two weeks back to six months ahead.
- Each meeting keeps its Clerk ID, so a time, date or room change **updates** the existing
  calendar event instead of adding a duplicate.
- Cancelled meetings stay on the calendar, titled `CANCELLED: …`.
- Event details include the Clerk's status, comment (e.g. public-comment deadlines),
  links to notices and agendas, and the meeting page.
- The file is only committed when the Clerk actually publishes a change, so the repo's
  commit history doubles as a log of schedule changes.
- The Clerk only publishes start times, so events default to 2 hours (4 for full Council).

## Subscribe in Outlook on the web

Calendar → **Add calendar** → **Subscribe from web** → paste the URL above → name it →
**Import**. Outlook refreshes subscribed calendars on Microsoft's schedule (typically a few
hours), and it can't be forced.

## Manual refresh

Actions tab → *Update council calendar feed* → **Run workflow**.

## Narrowing to specific committees

Edit the build step in `.github/workflows/update-feed.yml`, for example:

```
python3 build_ics.py --out docs/chicago-council.ics --bodies "City Council" "Committee on Transportation and Public Way" "Committee on Pedestrian and Traffic Safety"
```
