import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from pydantic import ValidationError
from app.db import Base
from app.models import CustomerModel, ProductModel, OrderModel
from app.customer_api import OrderRequest, AddressRequest, create_order
from app import reviewer

class CheckoutReplayTests(unittest.TestCase):
    def test_retry_reserves_stock_once(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine, expire_on_commit=False)
        customer = CustomerModel(phone='9876543210', name='Test')
        with sessions() as db:
            db.add(customer)
            db.add(ProductModel(name='Apple', unit='kg', price=100, stock_quantity=10, in_stock=True))
            db.commit()
            db.expunge(customer)
        payload = dict(items=[dict(name='Apple', unit='kg', price=1, quantity=1)], address='Talegaon 410507', payment_method='COD', idempotency_key='checkout_test_123456')
        with patch('app.customer_api.SessionLocal', sessions), patch('app.customer_api.notify_seller'):
            first = create_order(OrderRequest(**payload), customer)
            self.assertEqual(first, create_order(OrderRequest(**payload), customer))
            with sessions() as db:
                self.assertEqual(db.query(OrderModel).count(), 1)
                self.assertEqual(db.query(ProductModel).one().stock_quantity, 9)
            changed = dict(payload, payment_method='UPI')
            with self.assertRaises(HTTPException) as error:
                create_order(OrderRequest(**changed), customer)
            self.assertEqual(error.exception.status_code, 409)

    def test_invalid_pin(self):
        with self.assertRaises(ValidationError):
            AddressRequest(label='Home', address='Street', city='Talegaon', pincode='abcdef')
        with self.assertRaises(HTTPException):
            reviewer.require_service_area('Talegaon 999999', '9876543210')

    def test_configured_coverage(self):
        with patch.dict('os.environ', {'SERVICEABLE_PINCODES': '410507'}):
            reviewer.require_service_area('Talegaon 410507', '9876543210')
            with self.assertRaises(HTTPException):
                reviewer.require_service_area('PCMC 411033', '9876543210')
