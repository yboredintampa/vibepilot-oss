from db import get_cur
print("opening...")
with get_cur() as c:
    c.execute("select 1")
    print("ok", c.fetchone())
