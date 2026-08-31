import pandas as pd, json
p='2026.8.26瑞钧机械机床跟踪单.xlsx'
df=pd.read_excel(p,header=0)
print(json.dumps({'shape':df.shape,'columns':[str(c) for c in df.columns],'head':df.head(5).fillna('').to_dict('records'),'nonempty':{str(c):int(df[c].notna().sum()) for c in df.columns}},ensure_ascii=False,indent=2))