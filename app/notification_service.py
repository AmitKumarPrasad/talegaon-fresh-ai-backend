import json
import logging
import os
from typing import Optional

import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)


class NotificationService:
    """Manages FCM notifications for customers and delivery partners."""

    _initialized = False

    @staticmethod
    def _initialize_firebase():
        """Initialize Firebase Admin SDK if not already initialized."""
        if NotificationService._initialized:
            return

        try:
            # Initialize Firebase Admin SDK with service account key
            service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY_PATH")
            if not service_account_path:
                logger.warning("FIREBASE_SERVICE_ACCOUNT_KEY_PATH not set; FCM notifications disabled")
                return

            if not os.path.exists(service_account_path):
                logger.warning(f"Service account key file not found: {service_account_path}")
                return

            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
            NotificationService._initialized = True
            logger.info("Firebase Admin SDK initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Admin SDK: {str(e)}")

    @staticmethod
    def send_notification_to_customer(
        fcm_token: str,
        title: str,
        body: str,
        order_id: int,
        data: Optional[dict] = None,
    ) -> bool:
        """
        Send FCM notification to a customer.
        
        Args:
            fcm_token: Customer's FCM token
            title: Notification title
            body: Notification body/message
            order_id: Associated order ID
            data: Additional data payload
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not fcm_token:
            logger.warning(f"No FCM token available for customer notification")
            return False

        try:
            NotificationService._initialize_firebase()
            
            if not NotificationService._initialized:
                logger.warning("Firebase Admin SDK not initialized; notification not sent")
                return False

            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={
                    "order_id": str(order_id),
                    **(data or {})
                },
                token=fcm_token,
            )
            response = messaging.send(message)
            logger.info(f"Notification sent to customer: order_id={order_id}, response={response}")
            return True

        except Exception as e:
            logger.error(f"Failed to send customer notification: {str(e)}")
            return False

    @staticmethod
    def send_notification_to_partner(
        fcm_token: str,
        title: str,
        body: str,
        order_id: int,
        data: Optional[dict] = None,
    ) -> bool:
        """
        Send FCM notification to a delivery partner.
        
        Args:
            fcm_token: Partner's FCM token
            title: Notification title
            body: Notification body/message
            order_id: Associated order ID
            data: Additional data payload
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not fcm_token:
            logger.warning(f"No FCM token available for partner notification")
            return False

        try:
            NotificationService._initialize_firebase()
            
            if not NotificationService._initialized:
                logger.warning("Firebase Admin SDK not initialized; notification not sent")
                return False

            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={
                    "order_id": str(order_id),
                    **(data or {})
                },
                token=fcm_token,
            )
            response = messaging.send(message)
            logger.info(f"Notification sent to partner: order_id={order_id}, response={response}")
            return True

        except Exception as e:
            logger.error(f"Failed to send partner notification: {str(e)}")
            return False

    @staticmethod
    def notify_partner_new_order(
        partner_fcm_token: str, order_id: int, customer_name: str = "",
        delivery_address: str = "", total_amount: float | None = None,
    ) -> bool:
        """Broadcast availability without customer PII before assignment."""
        return NotificationService.send_notification_to_partner(
            fcm_token=partner_fcm_token,
            title="New Order",
            body="A new delivery order is available.",
            order_id=order_id,
            data={"order_id": str(order_id), "event_type": "new_order"},
        )

    @staticmethod
    def notify_customer_order_status(
        customer_fcm_token: str, order_id: int, new_status: str
    ) -> bool:
        """Notify a customer about order status change."""
        status_messages = {
            "CONFIRMED": "Your order has been confirmed",
            "PACKING": "Your order is being packed",
            "OUT_FOR_DELIVERY": "Your order is out for delivery",
            "DELIVERED": "Your order has been delivered",
            "CANCELLED": "Your order has been cancelled",
        }

        body = status_messages.get(new_status, f"Order status: {new_status}")
        return NotificationService.send_notification_to_customer(
            fcm_token=customer_fcm_token,
            title="Order Status Update",
            body=body,
            order_id=order_id,
            data={"order_id": str(order_id), "status": new_status, "event_type": "status_update"},
        )

    @staticmethod
    def notify_partner_assignment(
        partner_fcm_token: str, order_id: int, delivery_address: str
    ) -> bool:
        """Notify a delivery partner about delivery assignment."""
        return NotificationService.send_notification_to_partner(
            fcm_token=partner_fcm_token,
            title="Delivery Assignment",
            body=f"Delivery assigned: {delivery_address}",
            order_id=order_id,
            data={
                "order_id": str(order_id),
                "address": delivery_address,
                "event_type": "delivery_assignment",
            },
        )

    @staticmethod
    def notify_customer_delivery_partner(
        customer_fcm_token: str, order_id: int, partner_name: str, partner_phone: str
    ) -> bool:
        """Notify customer about assigned delivery partner."""
        return NotificationService.send_notification_to_customer(
            fcm_token=customer_fcm_token,
            title="Delivery Partner Assigned",
            body=f"{partner_name} will deliver your order",
            order_id=order_id,
            data={
                "order_id": str(order_id),
                "partner_name": partner_name,
                "partner_phone": partner_phone,
                "event_type": "partner_assigned",
            },
        )
