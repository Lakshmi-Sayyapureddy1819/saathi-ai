"""python -m services.lab_partner   -> serves the lab partner scheduling service (default 127.0.0.1:8100)."""
import logging
import os

import uvicorn

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from services.lab_partner.app import create_app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host=os.getenv("LAB_PARTNER_HOST", "127.0.0.1"),
                port=int(os.getenv("LAB_PARTNER_PORT", "8100")))
