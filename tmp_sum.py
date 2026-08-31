import pandas as pd, json
p='2026.8.26瑞钧机械机床跟踪单.xlsx'; d=pd.read_excel(p)
for i,c in enumerate(d.columns):
 s=d[c].dropna().astype(str)
 print(i,repr(c),'n=',len(s),'uniq=',s.nunique(),'samples=',s.head(3).tolist())