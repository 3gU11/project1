"""Supervisor smoke test: python -m contract_bridge (environment configured first)."""
from .worker import sync_once
from dotenv import load_dotenv

if __name__ == '__main__':
    load_dotenv()
    print(sync_once())
