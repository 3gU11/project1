families = ["中小型G", "中小型XS", "中大型XS", "中小型AUTO", "中大型AUTO", "特殊"]
for f in families:
    utf8_bytes = f.encode('utf-8')
    try:
        gbk_str = utf8_bytes.decode('gbk')
        print(f"{repr(f)} -> {repr(gbk_str)}")
    except Exception as e:
        print(f"Error for {repr(f)}: {e}")
