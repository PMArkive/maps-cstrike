import os
import glob
import html
import gzip
import minify_html
import sqlite3
import csv
import shutil
import json
import subprocess

"""
os.makedirs("processed/hashed", exist_ok=True)
os.makedirs("processed/maps", exist_ok=True)
"""

conn = sqlite3.connect("processed/maps.db")
cur = conn.cursor()
cur.executescript("""
DROP TABLE IF EXISTS maps_unfiltered;
DROP TABLE IF EXISTS maps_canon;
DROP TABLE IF EXISTS gamebanana;
DROP TABLE IF EXISTS links;

CREATE TABLE maps_unfiltered (mapname TEXT NOT NULL, filesize INT NOT NULL, filesize_bz2 INT NOT NULL, sha1 TEXT NOT NULL);
CREATE TABLE maps_canon (mapname TEXT NOT NULL, filesize INT NOT NULL, filesize_bz2 INT NOT NULL, sha1 TEXT NOT NULL);
CREATE TABLE gamebanana (sha1 TEXT NOT NULL, gamebananaid INT NOT NULL, gamebananafileid INT NOT NULL);
CREATE TABLE links (sha1 TEXT NOT NULL, url TEXT NOT NULL);

CREATE INDEX mapnameu ON maps_unfiltered(mapname);
CREATE INDEX sha1m on maps_unfiltered(sha1);
CREATE INDEX mapnamec ON maps_canon(mapname);
CREATE INDEX sha1c on maps_canon(sha1);
CREATE INDEX sha1g on gamebanana(sha1);
CREATE INDEX sha1o on links(sha1);
""")

# TODO: remerge maps table & add `canon` column to table...

gamebanana = {}
links = {}

unique = set()
for filename in glob.glob("unprocessed/*.csv"):
    with open(filename, newline='', encoding="utf-8") as f:
        cr = csv.reader(f)
        for line in cr:
            if line[0] == "mapname":
                continue
            thing = [x.lower() for x in line]
            thing[0] = thing[0].strip().replace('.', '_').replace(' ', '_') # because CS:S fails to download maps
            if len(thing) > 4:
                if thing[4].startswith("http://") or thing[4].startswith("https://"):
                    links[thing[3]] = thing[4]
                else:
                    # path & maybe gamebanana path...
                    splits = thing[4].split('_')
                    if splits[0].isdigit() and splits[1].isdigit(): # might have false positives...
                        gamebanana[thing[3]] = (int(splits[0]), int(splits[1]))
            unique.add(tuple(thing[:4]))

unfiltered = set(unique)
for filename in glob.glob("filters/*.csv"):
    with open(filename, newline='', encoding="utf-8") as f:
        cr = csv.reader(f)
        for line in cr:
            if line[0] == "mapname" or line[0].startswith("#"):
                continue
            thing = [x.lower() for x in line][:4]
            thing[0] = thing[0].strip().replace('.', '_').replace(' ', '_').strip() # because CS:S fails to download maps
            unique.remove(tuple(thing))
            #if line == "mapname,filesize,filesize_bz2,sha1\n":
            #    continue
            #unique.remove(line.lower().strip())

cur.executemany("INSERT INTO maps_unfiltered VALUES(?,?,?,?);", unfiltered)
cur.executemany("INSERT INTO maps_canon VALUES(?,?,?,?);", unique)
cur.executemany("INSERT INTO gamebanana VALUES(?,?,?);", [(a,b,c) for a, (b, c) in gamebanana.items()])
cur.executemany("INSERT INTO links VALUES(?,?);", [(a,b) for a, b in links.items()])

with open("canon.csv", encoding="utf-8") as f:
    #things = [[x.lower().strip() for x in line] for line in csv.reader(f)] # also newline='' in open
    things = [line.lower().strip().split(",")[:2] for line in f]
    things.pop(0) # remove "mapname,sha1,note"
    for x in things:
        if len(x[1]) != 40:
            raise Exception(f"fuck you {x}")
    cur.executemany("DELETE FROM maps_canon WHERE mapname = ? AND sha1 != ?;", things)
conn.commit() # fuck you for making me call you

recently_added = []
with open("recently_added.csv", newline='', encoding="utf-8") as f:
    cr = csv.reader(f)
    for line in cr:
        line[0] = line[0].lower().strip().replace('.', '_').replace(' ', '_').strip()
        recently_added.append(line)
    recently_added.pop(0) # remove "mapname,filesize,filesize_bz2,sha1,note,recently_added_note,datetime"

def create_thing(table, outfilename, canon, title, sqlwhere):
    res = cur.execute(f"SELECT COUNT(*), SUM(s1), SUM(s2) FROM (SELECT SUM(filesize) s1, SUM(filesize_bz2) s2 FROM {table} {sqlwhere} GROUP BY sha1);").fetchone()

    with open("index_top.html", encoding="utf-8") as f:
        index_html = """
        <!DOCTYPE html>
        <html>
        <head>
        <meta http-equiv="content-type" content="text/html; charset=utf-8">
        <meta name="viewport" content="width=device-width">
        <title>fastdl.me {}</title>
        """.format(title) + f.read() + """
        <h1>fastdl.me {}</h1>
        <h2><a href="https://fastdl.me">homepage</a></h2>
        <h3>Number of maps: {}</h3>
        <h3>Unpacked size: {:,} BYTES</h3>
        <h3>BZ2 size: {:,} BYTES</h3>
        <h4>(sorting is slow... you have been warned...)</h4>
        """.format(title, res[0], res[1], res[2])

    index_html += """
    <br>
    <h2>Recently added:</h2>
    (manually updated -- may be forgotten sometimes) <a href="https://github.com/srcwr/maps-cstrike/commits/master">(full commit history)</a>
    <table id="recentlyadded">
    <thead>
    <tr>
    <th style="width:1%">Map name</th>
    <th style="width:1%">Hash</th>
    <th style="width:15%">Note</th>
    <th style="width:4%">Datetime</th>
    <th style="width:1%">List of packed files</th>
    </tr>
    </thead>
    <tbody>
    """
    for x in recently_added:
        index_html += """
        <tr>
        <td><a href="#">{}</a></td>
        <td>{}</td>
        <td>{}</td>
        <td>{}</td>
        <td><a href="https://github.com/srcwr/maps-cstrike-more/blob/master/filelist/{}.csv">{}</a></td>
        </tr>
        """.format(html.escape(x[0]), x[3], x[5], x[6], x[3], html.escape(x[0]))

    index_html += '</tbody></table><br><br><br>'

    outf = open(f"processed/{outfilename}", "w+", encoding="utf-8")

    outf.write(index_html + """
    <table id="list" class="sortable">
    <thead>
    <tr>
    <th style="width:1%">Map name</th>
    <th style="width:5%">Hash</th>
    <th style="width:5%">Size bsp</th>
    <th style="width:5%">Size bz2</th>
    <th style="width:5%">Page</th>
    </tr>
    </thead>
    <tbody>
    """)

    if "canon" in title or table == "maps_unfiltered":
        outtextffff = open(f"processed/{outfilename}.txt", "w", newline="\n", encoding="utf-8")

    outcsvffff = open(f"processed/{outfilename}.csv", "w+", newline="", encoding="utf-8")
    mycsv = csv.writer(outcsvffff)
    mycsv.writerow(["mapname","sha1","filesize","filesize_bz2","url"])

    groupy = ""
    fzy = "filesize_bz2"
    if canon:
        groupy = "GROUP BY mapname"
        fzy = "MAX(filesize_bz2)"
    for row in cur.execute(f"""
        SELECT mapname, filesize, {fzy}, m.sha1, gamebananaid, url
        FROM {table} m
        LEFT JOIN gamebanana g ON g.sha1 = m.sha1
        LEFT JOIN links l ON l.sha1 = m.sha1
        {sqlwhere}
        {groupy}
        ORDER BY mapname;""").fetchall():
        link = row[5]
        htmllink = ""
        if link != None:
            htmllink = f'<td><a href="{link}">clickme</a></td>'
        else:
            gbid = row[4]
            if gbid != None:
                link = "https://gamebanana.com/mods/" + str(gbid)
                htmllink = f'<td><a href="{link}">{gbid}</a></td>'
        if "canon" in title:
            outtextffff.write(row[0] + "\n")
        elif table == "maps_unfiltered":
            outtextffff.write(row[3] + "\n")

        mycsv.writerow([row[0], row[3], row[1], row[2], link])
        if canon:
            index_html = """
            <tr>
            <td><a href="#">{}</a></td>
            <td>{}</td>
            <td>{}</td>
            <td>{}</td>
            {}
            </tr>
            """.format(html.escape(row[0]), row[3], row[1], row[2], htmllink)
        else:
            #<td><a href="#">{}</a></td>
            index_html = """
            <tr>
            <td><a href="#">{}</a></td>
            <td>{}</td>
            <td>{}</td>
            <td>{}</td>
            {}
            </tr>
            """.format(html.escape(row[0]), row[3], row[1], row[2], htmllink)
        outf.write(index_html)

    outf.seek(0)
    content = minify_html.minify(outf.read() + open("index_bottom.html", encoding="utf-8").read(), minify_js=True, minify_css=True)
    outf.seek(0)
    outf.truncate(0)
    outf.write(content)
    #"""
    with gzip.open(f"processed/{outfilename}.gz", "wt", encoding="utf-8") as g:
        g.write(content)
    #"""

try:
    shutil.rmtree("processed/check.fastdl.me")
except:
    pass
shutil.copytree("fastdlsite/check.fastdl.me", "processed/check.fastdl.me")
_things = {}
for row in cur.execute("SELECT mapname, filesize FROM maps_unfiltered"):
    if not row[0] in _things:
        _things[row[0]] = []
    _things[row[0]].append(int(row[1]))
with open("processed/check.fastdl.me/_thing.json", "w") as f:
    json.dump(_things, f)

try:
    shutil.rmtree("processed/fastdl.me")
except:
    pass
shutil.copytree("fastdlsite/fastdl.me", "processed/fastdl.me")

try:
    shutil.rmtree("processed/main.fastdl.me")
except:
    pass
shutil.copytree("fastdlsite/main.fastdl.me", "processed/main.fastdl.me")
shutil.copytree("../fastdl_opendir/materials", "processed/main.fastdl.me/materials")
shutil.copytree("../fastdl_opendir/sound", "processed/main.fastdl.me/sound")

# On Cloudflare: I have /maps/ rewritten to maps_index.html & /hashed/ rewritten to hashed_index.html....
create_thing("maps_unfiltered", "main.fastdl.me/hashed_index.html", False, "hashed/unfiltered maps", "")
create_thing("maps_canon", "main.fastdl.me/maps_index.html", True, "canon/filtered maps", "")
create_thing("maps_canon", "main.fastdl.me/69.html", True, "movement maps (mostly)", "WHERE mapname LIKE 'bh%' OR mapname LIKE 'xc\\_%' ESCAPE '\\' OR mapname LIKE 'kz%' OR mapname LIKE 'surf%' OR mapname LIKE 'trikz%' OR mapname LIKE 'jump%' OR mapname LIKE 'climb%' OR mapname LIKE 'fu\\_%' ESCAPE '\\' OR mapname LIKE '%hop%'")

# TODO: generate main.fastdl.me/index.html open directory pages

# what the fuck wrangler why won't my functions work otherwise
cwd = os.getcwd()
os.chdir("processed/check.fastdl.me")
subprocess.run("wrangler pages publish --project-name check-fastdl --branch main   .", shell=True)
os.chdir(cwd + "/processed/fastdl.me")
subprocess.run("wrangler pages publish --project-name fdl          --branch master .", shell=True)
os.chdir(cwd)

#wrangler pages publish --project-name fdl --branch master processed/fastdl.me
#wrangler pages publish --project-name mfdl --branch master processed/main.fastdl.me
