---
description: Verifica seguridad (Testnet, claves y Stop-Loss).
---

Haz una revisión crítica del código actual bajo la lupa de la gestión de riesgo. Verifica estrictamente tres cosas: 1) Que NO haya claves API (Keys/Secrets) escritas en el código. 2) Que las órdenes de compra/venta tengan un Stop-Loss matemático definido. 3) Que la conexión esté apuntando a la Testnet de Binance y no a la red real. Alerta de inmediato si falla alguna de estas tres reglas.