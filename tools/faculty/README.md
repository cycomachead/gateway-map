# faculty — who sits in which office

`import_faculty.py` turns the EECS faculty directory
(<https://www2.eecs.berkeley.edu/Faculty/Lists/faculty.html>) into
`src/data/gateway/occupants.ts`, the room-number → names map that the site uses to print
faculty names next to their office numbers, in the room list and details, and to find an
office by searching for a person. Only faculty whose office is in Gateway are kept.

## Re-querying the directory

```sh
npm run occupants                                        # fetch the live page and rewrite occupants.ts
python3 tools/faculty/import_faculty.py ~/faculty.html   # from a saved copy
python3 tools/faculty/import_faculty.py <source> <out>   # write somewhere else
```

Then review `git diff src/data/gateway/occupants.ts` and commit. The *Refresh faculty
occupants* GitHub Actions workflow (`.github/workflows/refresh-occupants.yml`) does the same
on the first of every month, or on demand from the Actions tab, and opens a pull request
when anything changed.

## How it reads the page

Standard library only. Every person on the page is one entry: an `<h3>` with a link to
their homepage under `/Faculty/Homepages/`, then a paragraph whose first line holds the
office and contact details (`4193 Gateway Building, 510-642-7034; …`). Office hours later in
the entry name Gateway classrooms, so only that contact line is searched for a room, written
as `4193 Gateway Building`, `Gateway Building 4193`, `Gateway 4193` or
`Gateway Building, Room 4193`. Names are taken as displayed; a `Last, First` entry is turned
around. If the page's layout changes so that no entries are found, the script stops with an
error instead of writing an empty file.

Rooms that are not on any floor of the map are listed in the browser console when the app
starts (and fail the `every room in the directory is on the map` end-to-end test), so a new
or renumbered office is easy to spot. People who are not on the directory page can be added
to the file by hand, but the next import overwrites it.
