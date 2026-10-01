from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.database.connection import SessionLocal
from app.database.models import (
    Company,
    Customer,
    Order,
    OrderEvent,
    OrderItem,
)


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "seed_data.json"


def load_seed_data() -> dict[str, Any]:
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Seed data file not found: {DATA_FILE}"
        )

    with DATA_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "Seed data must contain a JSON object."
        )

    return data


def parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None

    return datetime.fromisoformat(value)


def get_company_map(
    db,
    companies_data: list[dict[str, Any]],
) -> dict[str, Company]:

    company_map: dict[str, Company] = {}

    for item in companies_data:

        company_code = item["company_code"]

        company = db.scalar(
            select(Company).where(
                Company.company_code == company_code
            )
        )

        if company is None:
            company = Company(
                company_code=company_code,
                company_name=item["company_name"],
                domain=item.get("domain"),
                active=item.get("active", True),
                metadata_json=item.get("metadata_json"),
            )

            db.add(company)
            db.flush()

        else:
            company.company_name = item["company_name"]
            company.domain = item.get("domain")
            company.active = item.get("active", True)
            company.metadata_json = item.get("metadata_json")

        company_map[company_code] = company

    return company_map


def get_customer_map(
    db,
    customers_data: list[dict[str, Any]],
    company_map: dict[str, Company],
) -> dict[tuple[str, str], Customer]:

    customer_map: dict[tuple[str, str], Customer] = {}

    for item in customers_data:

        company_code = item["company_code"]
        customer_id = item["customer_id"]

        company = company_map[company_code]

        customer = db.scalar(
            select(Customer).where(
                Customer.company_id == company.id,
                Customer.customer_id == customer_id,
            )
        )

        if customer is None:

            customer = Customer(
                company_id=company.id,
                customer_id=customer_id,
                name=item.get("name"),
                email=item.get("email"),
                phone=item.get("phone"),
                address=item.get("address"),
                status=item.get("status", "active"),
                metadata_json=item.get("metadata_json"),
            )

            db.add(customer)
            db.flush()

        else:

            customer.name = item.get("name")
            customer.email = item.get("email")
            customer.phone = item.get("phone")
            customer.address = item.get("address")
            customer.status = item.get(
                "status",
                customer.status,
            )
            customer.metadata_json = item.get(
                "metadata_json"
            )

        customer_map[
            (company_code, customer_id)
        ] = customer

    return customer_map


def seed_orders(
    db,
    orders_data: list[dict[str, Any]],
    company_map: dict[str, Company],
    customer_map: dict[tuple[str, str], Customer],
) -> dict[tuple[str, str], Order]:

    order_map: dict[tuple[str, str], Order] = {}

    for item in orders_data:

        company_code = item["company_code"]
        customer_id = item["customer_id"]
        order_id = item["order_id"]

        company = company_map[company_code]

        customer = customer_map[
            (company_code, customer_id)
        ]

        order = db.scalar(
            select(Order).where(
                Order.company_id == company.id,
                Order.order_id == order_id,
            )
        )

        if order is None:

            order = Order(
                company_id=company.id,
                customer_id=customer.id,
                order_id=order_id,
                external_reference=item.get(
                    "external_reference"
                ),
                status=item["status"],
                payment_status=item.get(
                    "payment_status"
                ),
                fulfillment_status=item.get(
                    "fulfillment_status"
                ),
                currency=item.get(
                    "currency",
                    "INR",
                ),
                total_amount=Decimal(
                    str(item["total_amount"])
                ),
                shipping_address=item.get(
                    "shipping_address"
                ),
                tracking_number=item.get(
                    "tracking_number"
                ),
                estimated_delivery=parse_datetime(
                    item.get("estimated_delivery")
                ),
                delivered_at=parse_datetime(
                    item.get("delivered_at")
                ),
                cancellation_eligible=item.get(
                    "cancellation_eligible",
                    False,
                ),
                refund_eligible=item.get(
                    "refund_eligible",
                    False,
                ),
                return_eligible=item.get(
                    "return_eligible",
                    False,
                ),
                created_by=item.get("created_by"),
                updated_by=item.get("updated_by"),
                is_active=item.get(
                    "is_active",
                    True,
                ),
                source_system=item.get(
                    "source_system"
                ),
                last_verified_at=parse_datetime(
                    item.get("last_verified_at")
                ),
                metadata_json=item.get(
                    "metadata_json"
                ),
            )

            db.add(order)
            db.flush()

        else:

            order.customer_id = customer.id
            order.external_reference = item.get(
                "external_reference"
            )
            order.status = item["status"]
            order.payment_status = item.get(
                "payment_status"
            )
            order.fulfillment_status = item.get(
                "fulfillment_status"
            )
            order.currency = item.get(
                "currency",
                order.currency,
            )
            order.total_amount = Decimal(
                str(item["total_amount"])
            )
            order.shipping_address = item.get(
                "shipping_address"
            )
            order.tracking_number = item.get(
                "tracking_number"
            )
            order.estimated_delivery = parse_datetime(
                item.get("estimated_delivery")
            )
            order.delivered_at = parse_datetime(
                item.get("delivered_at")
            )
            order.cancellation_eligible = item.get(
                "cancellation_eligible",
                False,
            )
            order.refund_eligible = item.get(
                "refund_eligible",
                False,
            )
            order.return_eligible = item.get(
                "return_eligible",
                False,
            )
            order.created_by = item.get(
                "created_by"
            )
            order.updated_by = item.get(
                "updated_by"
            )
            order.is_active = item.get(
                "is_active",
                True,
            )
            order.source_system = item.get(
                "source_system"
            )
            order.last_verified_at = parse_datetime(
                item.get("last_verified_at")
            )
            order.metadata_json = item.get(
                "metadata_json"
            )

            db.flush()

        order_map[
            (company_code, order_id)
        ] = order

    return order_map


def seed_order_items(
    db,
    items_data: list[dict[str, Any]],
    order_map: dict[tuple[str, str], Order],
) -> None:

    for item in items_data:

        company_code = item["company_code"]
        order_id = item["order_id"]

        order = order_map[
            (company_code, order_id)
        ]

        existing = db.scalar(
            select(OrderItem).where(
                OrderItem.order_id == order.id,
                OrderItem.product_id
                == item.get("product_id"),
                OrderItem.product_name
                == item["product_name"],
            )
        )

        if existing is not None:
            existing.quantity = item.get(
                "quantity",
                1,
            )
            existing.unit_price = Decimal(
                str(item["unit_price"])
            )
            continue

        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item.get(
                    "product_id"
                ),
                product_name=item["product_name"],
                quantity=item.get(
                    "quantity",
                    1,
                ),
                unit_price=Decimal(
                    str(item["unit_price"])
                ),
            )
        )


def seed_order_events(
    db,
    events_data: list[dict[str, Any]],
    order_map: dict[tuple[str, str], Order],
) -> None:

    for item in events_data:

        company_code = item["company_code"]
        order_id = item["order_id"]

        order = order_map[
            (company_code, order_id)
        ]

        event_at = parse_datetime(
            item["event_at"]
        )

        existing = db.scalar(
            select(OrderEvent).where(
                OrderEvent.order_id == order.id,
                OrderEvent.event_type
                == item["event_type"],
                OrderEvent.event_at
                == event_at,
            )
        )

        if existing is not None:
            existing.description = item.get(
                "description"
            )
            existing.metadata_json = item.get(
                "metadata_json"
            )
            continue

        db.add(
            OrderEvent(
                order_id=order.id,
                event_type=item["event_type"],
                description=item.get(
                    "description"
                ),
                event_at=event_at,
                metadata_json=item.get(
                    "metadata_json"
                ),
            )
        )


def seed_database() -> None:

    data = load_seed_data()

    db = SessionLocal()

    try:

        companies_data = data.get(
            "companies",
            []
        )

        customers_data = data.get(
            "customers",
            []
        )

        orders_data = data.get(
            "orders",
            []
        )

        order_items_data = data.get(
            "order_items",
            []
        )

        order_events_data = data.get(
            "order_events",
            []
        )

        company_map = get_company_map(
            db,
            companies_data,
        )

        customer_map = get_customer_map(
            db,
            customers_data,
            company_map,
        )

        order_map = seed_orders(
            db,
            orders_data,
            company_map,
            customer_map,
        )

        seed_order_items(
            db,
            order_items_data,
            order_map,
        )

        seed_order_events(
            db,
            order_events_data,
            order_map,
        )

        db.commit()

        print(
            "Database seed completed successfully."
        )

        print(
            f"Companies processed: "
            f"{len(companies_data)}"
        )

        print(
            f"Customers processed: "
            f"{len(customers_data)}"
        )

        print(
            f"Orders processed: "
            f"{len(orders_data)}"
        )

        print(
            f"Order items processed: "
            f"{len(order_items_data)}"
        )

        print(
            f"Order events processed: "
            f"{len(order_events_data)}"
        )

    except Exception:

        db.rollback()
        raise

    finally:

        db.close()


if __name__ == "__main__":
    seed_database()