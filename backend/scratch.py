import asyncio
from database import MongoDB

async def main():
    mongodb = MongoDB()
    cursor = mongodb.db.users.find({"$or": [{"role": "teacher"}, {"role": "student"}]})
    docs = await cursor.to_list(None)
    print(f"Total users: {len(docs)}")
    for d in docs:
        print(f"Role: {d.get('role')}, School_id: {d.get('school_id')}, type: {type(d.get('school_id'))}")

    # let's also check admin
    admin = await mongodb.db.users.find_one({"role": "admin"})
    if admin:
        print(f"Admin school_id: {admin.get('school_id')}, type: {type(admin.get('school_id'))}")

asyncio.run(main())
