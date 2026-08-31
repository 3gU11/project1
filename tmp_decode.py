import pandas as pd
p='2026.8.26瑞钧机械机床跟踪单.xlsx'; d=pd.read_excel(p,header=0)
for c in d.columns:
 try: print(c, '=>', c.encode('latin1').decode('gbk'))
 except: print(c)