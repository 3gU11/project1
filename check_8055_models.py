import sys
sys.path.insert(0, '.')
from database import get_engine
from sqlalchemy import text

with get_engine().connect() as conn:
    # Check for 8055 models in the system
    result = conn.execute(text("""
        SELECT DISTINCT `机型`, COUNT(*) as count
        FROM finished_goods_data
        WHERE `机型` LIKE '%8055%' OR `机型` LIKE '%8060%' OR `机型` LIKE '%7055%'
        GROUP BY `机型`
        ORDER BY `机型`
    """))
    
    print("数据库中包含7055/8055/8060的机型:")
    print()
    for row in result:
        print(f"  {row[0]}: {row[1]}台")
    
    print()
    
    # Check in units table
    result2 = conn.execute(text("""
        SELECT DISTINCT model_type, COUNT(*) as count
        FROM units
        WHERE model_type LIKE '%8055%' OR model_type LIKE '%8060%' OR model_type LIKE '%7055%'
        GROUP BY model_type
        ORDER BY model_type
    """))
    
    print("units表中包含7055/8055/8060的机型:")
    print()
    for row in result2:
        print(f"  {row[0]}: {row[1]}台")
