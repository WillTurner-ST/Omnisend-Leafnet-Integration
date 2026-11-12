import argparse
import asyncio
import sys
import json
from middleware.config import settings
from middleware.services.contact_sync_service import ContactSyncService
from middleware.services.verification_service import VerificationService
from middleware.services.loyalty_service import LoyaltyService
from middleware.services.attribution_service import AttributionService


def run_sync(args):
    service = ContactSyncService()
    print(f"Starting {'FULL' if args.full else 'INCREMENTAL'} customer sync from NocoDB to Omnisend...")
    summary = asyncio.run(service.run_sync(full_sync=args.full))
    print("\n--- Sync Summary ---")
    print(f"Total fetched from NocoDB: {summary.total_fetched}")
    print(f"Synced to Omnisend:        {summary.synced_to_omnisend}")
    print(f"Skipped (No Email):        {summary.skipped_no_email}")
    print(f"Skipped (Invalid Email):   {summary.skipped_invalid_email}")
    print(f"Skipped (Opted Out):       {summary.skipped_opted_out}")
    print(f"Failed Records:            {summary.failed_records}")
    print(f"Success Status:            {'SUCCESS' if summary.success else 'FAILED'}")
    if summary.errors:
        print(f"Errors ({len(summary.errors)}):")
        for err in summary.errors[:10]:
            print(f"  - {err}")


def run_verify(args):
    service = VerificationService()
    print(f"Checking parity for customer {args.customer_id} across Leafnet & NocoDB...")
    res = asyncio.run(service.verify_customer_parity(args.customer_id))
    print(json.dumps(res, indent=2))


def run_loyalty_lookup(args):
    service = LoyaltyService()
    print(f"Looking up loyalty points and history for phone: {args.phone}...")
    res = asyncio.run(service.get_loyalty_balance(phone=args.phone, get_history=args.history))
    print(json.dumps(res.model_dump(), indent=2))


def run_phone_only_report(args):
    service = AttributionService()
    print("Fetching phone-only customer audit report by store location...")
    reports = service.get_phone_only_store_report()
    if not reports:
        print("No phone-only customers found in local store audit log.")
        return
    print(f"\n{'Store Location':<25} | {'Phone-Only Count':<18}")
    print("-" * 47)
    for r in reports:
        print(f"{r.store_location:<25} | {r.phone_only_count:<18}")


def run_server(args):
    import uvicorn
    host = args.host or settings.host
    port = args.port or settings.port
    print(f"Starting Leafnet/NocoDB to Omnisend Middleware on {host}:{port}...")
    uvicorn.run("middleware.main:app", host=host, port=port, reload=args.reload)


def main():
    parser = argparse.ArgumentParser(
        description="Leafnet & NocoDB into Omnisend Middleware CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Sync
    sync_parser = subparsers.add_parser("sync", help="Run customer synchronization from NocoDB to Omnisend")
    sync_parser.add_argument("--full", action="store_true", help="Perform full sync instead of incremental")
    sync_parser.set_defaults(func=run_sync)

    # Verify
    verify_parser = subparsers.add_parser("verify", help="Verify customer data parity across Leafnet and NocoDB")
    verify_parser.add_argument("--customer-id", required=True, help="Leafnet Customer ID to check")
    verify_parser.set_defaults(func=run_verify)

    # Loyalty Lookup
    loyalty_parser = subparsers.add_parser("loyalty-lookup", help="Look up points and ledger for a phone number")
    loyalty_parser.add_argument("--phone", required=True, help="Customer phone number")
    loyalty_parser.add_argument("--history", action="store_true", help="Include points ledger history")
    loyalty_parser.set_defaults(func=run_loyalty_lookup)

    # Phone-only Report
    report_parser = subparsers.add_parser("report-phone-only", help="Report customers with phone but missing email")
    report_parser.set_defaults(func=run_phone_only_report)

    # Server
    serve_parser = subparsers.add_parser("serve", help="Start the FastAPI webhook and REST server")
    serve_parser.add_argument("--host", default=None, help="Host address to bind")
    serve_parser.add_argument("--port", type=int, default=None, help="Port to bind")
    serve_parser.add_argument("--reload", action="store_true", help="Enable live reload for development")
    serve_parser.set_defaults(func=run_server)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
