# Architecture

Customer WhatsApp messages will enter the FastAPI webhook, then be routed through the OpenAI-powered conversation layer. Business operations such as pricing, minimum-order validation, and order persistence will remain server-side functions.

## Initial flow
WhatsApp -> FastAPI webhook -> conversation service -> business functions -> MySQL
