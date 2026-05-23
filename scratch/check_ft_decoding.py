import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from database import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    row = conn.execute(text("SELECT model_name, model_family, HEX(model_family) FROM model_dictionary WHERE model_name = 'FT'")).fetchone()
    print("Row:", row)
    if row:
        name, family, hex_val = row
        print(f"model_name: {repr(name)}")
        print(f"model_family type: {type(family)}")
        print(f"model_family repr: {repr(family)}")
        print(f"model_family hex: {hex_val}")
        # Test encoding/decoding if it's a string
        if isinstance(family, str):
            try:
                # If it was decoded with latin1/GBK but stored as UTF-8, we can reconstruct it:
                print("Decoded as latin1 then encoded to bytes then decoded as utf-8:")
                b = family.encode('latin1')
                print("  latin1-bytes:", b.hex())
                print("  utf8-decoded:", b.decode('utf-8'))
            except Exception as e:
                print("  latin1 conversion error:", e)
            try:
                b2 = family.encode('gbk')
                print("  gbk-bytes:", b2.hex())
                print("  utf8-decoded:", b2.decode('utf-8'))
            except Exception as e:
                print("  gbk conversion error:", e)
