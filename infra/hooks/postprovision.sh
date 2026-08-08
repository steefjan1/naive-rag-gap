#!/bin/sh
# Writes .env from the azd environment so the samples run without further setup.
set -e

azd env get-values > .env

echo ""
echo "Wrote .env from the azd environment."
echo "Next:"
echo "  python -m 01_retrieval.create_index"
echo "  python -m 01_retrieval.index_documents"
echo "  python -m 01_retrieval.compare_retrieval"
echo ""
echo "Role assignments can take a few minutes to propagate. A 403 on the"
echo "first run usually means wait, not misconfigured."
