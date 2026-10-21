import sys
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.db import Base, SessionLocal
from app.main import app
from app.models import ProductModel, OrderModel, OrderItemModel
from app.reviewer import ReviewerOrderModel

@pytest.fixture()
def review(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    factory=sessionmaker(bind=engine,autoflush=False)
    Base.metadata.create_all(engine)
    for name,module in list(sys.modules.items()):
        if name.startswith('app.') and getattr(module,'SessionLocal',None) is SessionLocal:
            monkeypatch.setattr(module,'SessionLocal',factory)
    monkeypatch.setenv('JWT_SECRET','review-test-secret')
    monkeypatch.setenv('ENVIRONMENT','development')
    monkeypatch.setenv('REVIEWER_CUSTOMER_PHONES','9888888888')
    with factory() as db:
        db.add(ProductModel(name='Tomato',unit='1 kg',price=40,in_stock=True,stock_quantity=10));db.commit()
    yield TestClient(app),factory

def auth(client,phone):
    r=client.post('/auth/register',json={'phone':phone,'pin':'384719','name':'Review Test','device_id':'review-test-device-id'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['access_token']},r.json()

def payload(address):
    return {'items':[{'name':'Tomato','unit':'1 kg','price':1,'quantity':2}],'address':address,'payment_method':'COD'}

def test_reviewer_worldwide_isolated_and_authenticated(review):
    client,factory=review
    headers,login=auth(client,'9888888888');other,_=auth(client,'9777777777')
    assert login['customer']['is_reviewer']
    with patch('app.customer_api.notify_seller') as seller,patch('app.customer_api.NotificationService.notify_partner_new_order') as partner:
        r=client.post('/customers/me/orders',headers=headers,json=payload('Review address, London'))
        assert r.status_code==200,r.text
        demo=r.json();oid=demo['order_id']
        assert demo['is_demo'] and demo['total']==100 and demo['status']=='DELIVERED'
        seller.assert_not_called();partner.assert_not_called()
    with factory() as db:
        assert db.query(OrderModel).count()==db.query(OrderItemModel).count()==0
        assert db.query(ReviewerOrderModel).count()==1
        assert db.query(ProductModel).one().stock_quantity==10
    assert client.get('/customers/me/orders',headers=headers).json()['orders'][0]['order_id']==oid
    assert client.get(f'/customers/me/orders/{oid}',headers=other).status_code==404
    assert client.get(f'/customers/me/orders/{oid}/tracking',headers=headers).json()['status']=='DELIVERED'
    assert client.get(f'/customers/me/orders/{oid}/status-history',headers=headers).json()['history']
    assert client.post(f'/customers/me/orders/{oid}/messages',headers=headers,json={'message':'Demo question'}).status_code==200
    assert len(client.get(f'/customers/me/orders/{oid}/messages',headers=headers).json()['messages'])==1
    assert client.post(f'/customers/me/orders/{oid}/product-request',headers=headers,json={'request_text':'Demo suggestion'}).status_code==200
    assert client.post(f'/customers/me/orders/{oid}/payment-link',headers=headers).status_code==400
    assert client.get('/customers/me/orders').status_code==401
    assert client.post('/auth/login',json={'phone':'9888888888','pin':'000000','device_id':'review-test-device-id'}).status_code==401

@pytest.mark.parametrize('address',['House 1, Talegaon Dabhade, 410507','House 2, Ravet, 412101','House 3, PCMC, 411033','House 4, Pimpri-Chinchwad, 411017','House 5, Nigdi, 411044','House 6, Wakad, 411057','House 7, Kothrud, Pune, 411038','House 8, Hadapsar, Pune, 411028','House 9, Pune, 411001'])
def test_real_localities_stock(review,address):
    client,factory=review;headers,login=auth(client,'9777777777')
    assert not login['customer']['is_reviewer']
    with patch('app.customer_api.notify_seller'):
        r=client.post('/customers/me/orders',headers=headers,json=payload(address))
    assert r.status_code==200,r.text
    with factory() as db:
        assert db.query(OrderModel).count()==1 and db.query(ReviewerOrderModel).count()==0
        assert db.query(ProductModel).one().stock_quantity==8

@pytest.mark.parametrize('address',['Mumbai 400001','Satara 415001','Solapur 413001','Nashik 422001','Address without a PIN'])
def test_other_areas_rejected(review,address):
    client,factory=review;headers,_=auth(client,'9777777777')
    assert client.post('/customers/me/orders',headers=headers,json=payload(address)).status_code==400
    with factory() as db:
        assert db.query(OrderModel).count()==0 and db.query(ProductModel).one().stock_quantity==10
