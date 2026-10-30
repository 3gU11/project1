import sys,pathlib,subprocess,os,json,time,urllib.request
sys.path.insert(0,'F:/work/aftercare/aftercare/output/deployment-tools')
import psutil
root=pathlib.Path('F:/work/V8/project1')
listeners={c.pid for c in psutil.net_connections(kind='tcp') if c.laddr.port==8000 and c.status=='LISTEN'}
assert len(listeners)==1
p=psutil.Process(listeners.pop());args=p.cmdline();env=p.environ();cwd=p.cwd()
assert pathlib.Path(cwd)==root and 'uvicorn' in args
probe="from crud.dealer_orders import list_dealer_orders,preview_dealer_order; r=list_dealer_orders(page_size=2); print('orders_read_ok',r['total']); rows=r['data']; n=rows[0]['order_no'] if rows else None; print('preview_read_ok',bool(preview_dealer_order(n)) if n else 'no orders')"
r=subprocess.run([args[0],'-c',probe],cwd=cwd,env=env,capture_output=True,text=True)
print(r.stdout.strip());assert r.returncode==0,'Read validation failed; runtime not restarted'
p.terminate();p.wait(timeout=20)
with open(root/'api-schema-retry.out.log','ab') as out,open(root/'api-schema-retry.err.log','ab') as err:
 child=subprocess.Popen(args,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
for attempt in range(40):
 if child.poll() is not None:raise RuntimeError('API exited; inspect local logs')
 try:
  with urllib.request.urlopen('http://127.0.0.1:8000/openapi.json',timeout=2) as response:
   if response.status==200:break
 except OSError:time.sleep(1)
else:raise RuntimeError('API startup not confirmed')
print(json.dumps({'deployed':True,'pid':child.pid,'openapi':200,'databaseMutation':False}))
