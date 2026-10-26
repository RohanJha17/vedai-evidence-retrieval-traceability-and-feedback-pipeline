from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run("panchakarma_evidence.api:app", host="0.0.0.0", port=int(os.getenv("PORT", "4100")))
