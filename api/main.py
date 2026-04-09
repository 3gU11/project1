from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import inventory, users, auth, planning, logs, traceability

app = FastAPI(
    title="V7ex API",
    description="FastAPI layer for the Finished Goods Management System",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(inventory.router, prefix="/api/v1/inventory", tags=["Inventory"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(planning.router, prefix="/api/v1/planning", tags=["Planning"])
app.include_router(logs.router, prefix="/api/v1/logs", tags=["Logs"])
app.include_router(traceability.router, prefix="/api/v1/traceability", tags=["Traceability"])

@app.get("/health")
def health_check():
    return {"status": "ok"}
