"""
Test end-to-end completo:
- Crear stand con inversión
- Crear 3 integrantes
- Crear 3 productos (uno con stock)
- Crear 1 promoción
- Crear sesión, abrir, asignar integrantes
- Crear ventas variadas (con promo, con precio cambiado + nota REMATE, diferentes pagos)
- Marcar pagos y entregas
- Verificar resumen financiero
- Exportar Excel de sesión y validar contenido
"""
import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

# Use a temporary test database
TEST_DB = tempfile.mktemp(suffix='.db')
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DB}'

from app import create_app, db
from models import (Stand, Producto, Promocion, Venta, DetalleVenta,
                    Integrante, SesionVenta, SesionIntegrante)

CHILE_TZ = ZoneInfo('America/Santiago')
PASS = '\033[92mPASS\033[0m'
FAIL = '\033[91mFAIL\033[0m'
errors = []


def check(desc, condition, detail=''):
    if condition:
        print(f'  {PASS}  {desc}')
    else:
        msg = f'{desc} — {detail}' if detail else desc
        print(f'  {FAIL}  {msg}')
        errors.append(msg)


def main():
    app = create_app()
    client = app.test_client()

    with app.app_context():
        # ============================================================
        print('\n' + '='*60)
        print('1. CREAR STAND')
        print('='*60)
        resp = client.post('/crear-stand', data={
            'nombre': 'Feria Test E2E',
        }, follow_redirects=False)
        check('POST /crear-stand → 302', resp.status_code == 302)

        stand = Stand.query.first()
        check('Stand creado en DB', stand is not None)
        check(f'Código de acceso: {stand.codigo_acceso}', len(stand.codigo_acceso) == 6)
        codigo = stand.codigo_acceso

        # Inversión ahora es por sesión, no por stand

        # ============================================================
        print('\n' + '='*60)
        print('2. CREAR 3 INTEGRANTES')
        print('='*60)
        integrantes_data = [
            {'nombre': 'Ana García', 'telefono': '+56912345678'},
            {'nombre': 'Carlos López', 'telefono': '+56987654321'},
            {'nombre': 'María Rodríguez', 'telefono': ''},
        ]
        for data in integrantes_data:
            resp = client.post(f'/s/{codigo}/integrantes', data=data, follow_redirects=True)
            check(f'Integrante "{data["nombre"]}" creado', resp.status_code == 200)

        integrantes = Integrante.query.filter_by(stand_id=stand.id).all()
        check(f'Total integrantes: {len(integrantes)}', len(integrantes) == 3)

        # ============================================================
        print('\n' + '='*60)
        print('3. CREAR 3 PRODUCTOS')
        print('='*60)
        productos_data = [
            {'nombre': 'Empanada de Pino', 'precio': '2500', 'stock': ''},
            {'nombre': 'Choripán', 'precio': '3000', 'stock': '20'},
            {'nombre': 'Jugo Natural', 'precio': '1500', 'stock': '50'},
        ]
        for data in productos_data:
            resp = client.post(f'/s/{codigo}/productos', data=data, follow_redirects=True)
            check(f'Producto "{data["nombre"]}" (${ int(data["precio"]):,}) creado', resp.status_code == 200)

        productos = Producto.query.filter_by(stand_id=stand.id, activo=True).all()
        check(f'Total productos activos: {len(productos)}', len(productos) == 3)

        empanada = Producto.query.filter_by(nombre='Empanada de Pino').first()
        choripan = Producto.query.filter_by(nombre='Choripán').first()
        jugo = Producto.query.filter_by(nombre='Jugo Natural').first()

        check('Empanada: stock ilimitado (NULL)', empanada.stock is None)
        check(f'Choripán: stock = {choripan.stock}', choripan.stock == 20)
        check(f'Jugo: stock = {jugo.stock}', jugo.stock == 50)

        # ============================================================
        print('\n' + '='*60)
        print('4. CREAR PROMOCIÓN: 3 Empanadas x $5.000')
        print('='*60)
        resp = client.post(f'/s/{codigo}/promociones', data={
            'producto_id': str(empanada.id),
            'cantidad': '3',
            'precio_promocion': '5000',
        }, follow_redirects=True)
        check('Promoción creada', resp.status_code == 200)

        promo = Promocion.query.filter_by(stand_id=stand.id).first()
        check(f'Promoción: {promo.nombre}', promo is not None)
        check(f'  producto_id = Empanada ({empanada.id})', promo.producto_id == empanada.id)
        check(f'  cantidad = {promo.cantidad}', promo.cantidad == 3)
        check(f'  precio_promo = ${promo.precio_promocion:,}', promo.precio_promocion == 5000)

        # ============================================================
        print('\n' + '='*60)
        print('5. CREAR SESIÓN Y ABRIR')
        print('='*60)
        hoy = date.today().isoformat()
        resp = client.post(f'/s/{codigo}/sesiones/nueva', data={
            'fecha': hoy,
            'nombre': 'Feria Prueba Completa',
        }, follow_redirects=False)
        check('Sesión creada → redirect', resp.status_code == 302)

        sesion = SesionVenta.query.filter_by(stand_id=stand.id).first()
        check(f'Sesión en DB: "{sesion.nombre}"', sesion is not None)
        check(f'Estado inicial: {sesion.estado}', sesion.estado == 'programada')

        # Abrir sesión
        resp = client.post(f'/s/{codigo}/sesiones/{sesion.id}/estado', data={
            'estado': 'abierta',
        }, follow_redirects=True)
        db.session.refresh(sesion)
        check(f'Estado después de abrir: {sesion.estado}', sesion.estado == 'abierta')

        # ============================================================
        print('\n' + '='*60)
        print('6. ASIGNAR INTEGRANTES A SESIÓN')
        print('='*60)
        form_data = {}
        for i, integrante in enumerate(integrantes):
            if i == 0:  # Ana - cocina
                form_data[f'roles_{integrante.id}'] = 'cocina'
            elif i == 1:  # Carlos - atención + entrega
                form_data[f'roles_{integrante.id}'] = ['atencion', 'entrega']
            else:  # María - atención
                form_data[f'roles_{integrante.id}'] = 'atencion'

        resp = client.post(f'/s/{codigo}/sesiones/{sesion.id}/integrantes',
                           data=form_data, follow_redirects=True)
        check('Roles asignados', resp.status_code == 200)

        asignaciones = SesionIntegrante.query.filter_by(sesion_id=sesion.id).all()
        check(f'Total asignaciones: {len(asignaciones)}', len(asignaciones) == 4)
        roles = [(a.integrante.nombre, a.rol) for a in asignaciones]
        check('Ana → cocina', ('Ana García', 'cocina') in roles)
        check('Carlos → atencion', ('Carlos López', 'atencion') in roles)
        check('Carlos → entrega', ('Carlos López', 'entrega') in roles)
        check('María → atencion', ('María Rodríguez', 'atencion') in roles)

        # ============================================================
        print('\n' + '='*60)
        print('7. CREAR VENTAS')
        print('='*60)

        # --- Venta 1: Normal, 2 empanadas + 1 choripán, efectivo ---
        print('\n  --- Venta 1: Normal (2 Empanadas + 1 Choripán), Efectivo ---')
        items_v1 = json.dumps([
            {'producto_id': empanada.id, 'cantidad': 2, 'precio': 2500},
            {'producto_id': choripan.id, 'cantidad': 1, 'precio': 3000},
        ])
        # total = 2*2500 + 1*3000 = 8000
        resp = client.post(f'/s/{codigo}/ventas/nueva', data={
            'cliente_nombre': 'Pedro Sánchez',
            'metodo_pago': 'efectivo',
            'notas': '',
            'total_final': '8000',
            'items': items_v1,
            'sesion_id': str(sesion.id),
        }, follow_redirects=False)
        check('Venta 1 creada → redirect', resp.status_code == 302)

        v1 = Venta.query.filter_by(stand_id=stand.id, numero_orden=1).first()
        check(f'Venta #1: cliente={v1.cliente_nombre}', v1.cliente_nombre == 'Pedro Sánchez')
        check(f'  total_final=${v1.total_final:,}', v1.total_final == 8000)
        check(f'  metodo_pago={v1.metodo_pago}', v1.metodo_pago == 'efectivo')
        check(f'  sesion_id={v1.sesion_id}', v1.sesion_id == sesion.id)
        check(f'  detalles: {len(v1.detalles)} items', len(v1.detalles) == 2)

        # --- Venta 2: CON PROMOCIÓN, 6 empanadas (2 batches x 3), transferencia ---
        print('\n  --- Venta 2: Con PROMO (6 Empanadas = 2x promo), Transferencia ---')
        items_v2 = json.dumps([
            {'producto_id': empanada.id, 'cantidad': 6, 'precio': 2500},
        ])
        # Promo: 3x$5000, 6 empanadas = 2 batches * $5000 = $10.000 (vs 6*2500=$15.000)
        resp = client.post(f'/s/{codigo}/ventas/nueva', data={
            'cliente_nombre': 'Luisa Martínez',
            'metodo_pago': 'transferencia',
            'notas': 'Cliente frecuente',
            'total_final': '10000',
            'items': items_v2,
            'sesion_id': str(sesion.id),
        }, follow_redirects=False)
        check('Venta 2 creada', resp.status_code == 302)

        v2 = Venta.query.filter_by(stand_id=stand.id, numero_orden=2).first()
        check(f'Venta #2: total_final=${v2.total_final:,}', v2.total_final == 10000)
        d2 = v2.detalles[0]
        check(f'  Subtotal con promo: ${d2.subtotal:,} (esperado $10.000)', d2.subtotal == 10000)
        check(f'  promo_texto: {d2.promocion_texto}', d2.promocion_texto is not None)
        check(f'  promo_id vinculado', d2.promocion_id == promo.id)

        # --- Venta 3: REMATE - precio rebajado + nota, efectivo ---
        print('\n  --- Venta 3: REMATE (Choripán a $1.500 + Jugo a $500), Efectivo ---')
        items_v3 = json.dumps([
            {'producto_id': choripan.id, 'cantidad': 3, 'precio': 1500},
            {'producto_id': jugo.id, 'cantidad': 4, 'precio': 500},
        ])
        # total = 3*1500 + 4*500 = 4500 + 2000 = 6500
        resp = client.post(f'/s/{codigo}/ventas/nueva', data={
            'cliente_nombre': 'Roberto Díaz',
            'metodo_pago': 'efectivo',
            'notas': 'REMATE - cierre de feria, precios rebajados',
            'total_final': '6500',
            'items': items_v3,
            'sesion_id': str(sesion.id),
        }, follow_redirects=False)
        check('Venta 3 (REMATE) creada', resp.status_code == 302)

        v3 = Venta.query.filter_by(stand_id=stand.id, numero_orden=3).first()
        check(f'Venta #3: total_final=${v3.total_final:,}', v3.total_final == 6500)
        check(f'  notas: "{v3.notas}"', 'REMATE' in (v3.notas or ''))
        d3_chori = [d for d in v3.detalles if d.nombre_producto == 'Choripán'][0]
        check(f'  Choripán precio rebajado: ${d3_chori.precio_unitario:,} (original $3.000)',
              d3_chori.precio_unitario == 1500)
        d3_jugo = [d for d in v3.detalles if d.nombre_producto == 'Jugo Natural'][0]
        check(f'  Jugo precio rebajado: ${d3_jugo.precio_unitario:,} (original $1.500)',
              d3_jugo.precio_unitario == 500)

        # --- Venta 4: Mixta, transferencia, con 4 empanadas (1 batch promo + 1 extra) ---
        print('\n  --- Venta 4: Mixta (4 Empanadas + 2 Jugos), Transferencia ---')
        items_v4 = json.dumps([
            {'producto_id': empanada.id, 'cantidad': 4, 'precio': 2500},
            {'producto_id': jugo.id, 'cantidad': 2, 'precio': 1500},
        ])
        # Empanada: 1 batch (3x$5000) + 1 extra ($2500) = $7500
        # Jugo: 2*$1500 = $3000
        # Total = $10.500
        resp = client.post(f'/s/{codigo}/ventas/nueva', data={
            'cliente_nombre': 'Sofía Vargas',
            'metodo_pago': 'transferencia',
            'notas': '',
            'total_final': '10500',
            'items': items_v4,
            'sesion_id': str(sesion.id),
        }, follow_redirects=False)
        check('Venta 4 creada', resp.status_code == 302)

        v4 = Venta.query.filter_by(stand_id=stand.id, numero_orden=4).first()
        d4_emp = [d for d in v4.detalles if d.nombre_producto == 'Empanada de Pino'][0]
        check(f'Venta #4: total=${v4.total_final:,}', v4.total_final == 10500)
        check(f'  Empanada subtotal con promo: ${d4_emp.subtotal:,} (1batch $5000 + 1x$2500 = $7500)',
              d4_emp.subtotal == 7500)

        # ============================================================
        print('\n' + '='*60)
        print('8. VERIFICAR STOCK')
        print('='*60)
        resp = client.get(f'/s/{codigo}/stock')
        stock_data = resp.get_json()
        check('API /stock responde JSON', isinstance(stock_data, list))

        choripan_stock = [s for s in stock_data if s['nombre'] == 'Choripán'][0]
        # Choripán: vendidos = 1 (v1) + 3 (v3) = 4, disponible = 20-4 = 16
        check(f'Choripán: vendido={choripan_stock["vendido"]}, disponible={choripan_stock["disponible"]}',
              choripan_stock['vendido'] == 4 and choripan_stock['disponible'] == 16)

        jugo_stock = [s for s in stock_data if s['nombre'] == 'Jugo Natural'][0]
        # Jugo: vendidos = 4 (v3) + 2 (v4) = 6, disponible = 50-6 = 44
        check(f'Jugo: vendido={jugo_stock["vendido"]}, disponible={jugo_stock["disponible"]}',
              jugo_stock['vendido'] == 6 and jugo_stock['disponible'] == 44)

        # ============================================================
        print('\n' + '='*60)
        print('9. ACTUALIZAR PAGOS Y ENTREGAS')
        print('='*60)

        # Marcar Venta 1 como pagada y entregada
        resp = client.post(f'/s/{codigo}/ventas/{v1.id}/marcar-pagado', follow_redirects=True)
        db.session.refresh(v1)
        check(f'Venta #1 pagada: estado_pago={v1.estado_pago}', v1.estado_pago == 'pagado')
        check(f'  monto_pagado=${v1.monto_pagado:,}', v1.monto_pagado == 8000)

        resp = client.post(f'/s/{codigo}/ventas/{v1.id}/marcar-entregado', follow_redirects=True)
        db.session.refresh(v1)
        check(f'Venta #1 entregada: estado_entrega={v1.estado_entrega}', v1.estado_entrega == 'entregado')

        # Marcar Venta 2 como pagada, entrega = listo
        resp = client.post(f'/s/{codigo}/ventas/{v2.id}/marcar-pagado', follow_redirects=True)
        resp = client.post(f'/s/{codigo}/ventas/{v2.id}/estado', data={
            'estado_entrega': 'listo'
        }, follow_redirects=True)
        db.session.refresh(v2)
        check(f'Venta #2 pagada, entrega listo: pago={v2.estado_pago}, entrega={v2.estado_entrega}',
              v2.estado_pago == 'pagado' and v2.estado_entrega == 'listo')

        # Venta 3: pago parcial ($3000 de $6500)
        resp = client.post(f'/s/{codigo}/ventas/{v3.id}', data={
            'estado_pago': 'parcial',
            'monto_pagado': '3000',
            'estado_entrega': 'entregado',
            'total_final': '6500',
            'notas': 'REMATE - cierre de feria, precios rebajados',
        }, follow_redirects=True)
        db.session.refresh(v3)
        check(f'Venta #3 parcial (${v3.monto_pagado:,}/${v3.total_final:,}), entregado',
              v3.estado_pago == 'parcial' and v3.monto_pagado == 3000 and v3.estado_entrega == 'entregado')

        # Venta 4: pendiente
        db.session.refresh(v4)
        check(f'Venta #4 pendiente pago y entrega',
              v4.estado_pago == 'pendiente' and v4.estado_entrega == 'pendiente')

        # ============================================================
        print('\n' + '='*60)
        print('10. VERIFICAR RESUMEN FINANCIERO')
        print('='*60)

        total_recaudado = v1.total_final + v2.total_final + v3.total_final + v4.total_final
        total_pagado = v1.monto_pagado + v2.monto_pagado + v3.monto_pagado + v4.monto_pagado
        pendiente_cobro = total_recaudado - total_pagado

        check(f'Total recaudado: ${total_recaudado:,} (8k+10k+6.5k+10.5k = $35.000)',
              total_recaudado == 35000)
        check(f'Total pagado: ${total_pagado:,} (8k+10k+3k+0 = $21.000)',
              total_pagado == 21000)
        check(f'Pendiente cobro: ${pendiente_cobro:,} ($14.000)',
              pendiente_cobro == 14000)

        # Efectivo: v1($8000) + v3($6500) = $14.500 (2 ventas)
        # Transferencia: v2($10000) + v4($10.500) = $20.500 (2 ventas)
        monto_efectivo = v1.total_final + v3.total_final
        monto_transferencia = v2.total_final + v4.total_final
        check(f'Efectivo: ${monto_efectivo:,} (2 ventas)', monto_efectivo == 14500)
        check(f'Transferencia: ${monto_transferencia:,} (2 ventas)', monto_transferencia == 20500)

        # ============================================================
        print('\n' + '='*60)
        print('11. VERIFICAR VISTA DE SESIÓN')
        print('='*60)
        resp = client.get(f'/s/{codigo}/sesiones/{sesion.id}')
        check('GET sesión detalle → 200', resp.status_code == 200)
        html = resp.data.decode('utf-8')
        check('"Feria Prueba Completa" en HTML', 'Feria Prueba Completa' in html)
        check('"$35.000" (total) en HTML', '35.000' in html or '35,000' in html)
        check('"Pedro Sánchez" (cliente v1) en HTML', 'Pedro' in html)
        # Notas no se muestran en la vista de sesión (sí en Excel y detalle individual)
        # Verificamos que la vista carga correctamente con las 4 ventas
        check('4 ventas visibles en sesión', 'Pedro' in html and 'Luisa' in html and 'Roberto' in html)

        # ============================================================
        print('\n' + '='*60)
        print('12. VERIFICAR COCINA API')
        print('='*60)
        resp = client.get(f'/s/{codigo}/cocina/api')
        cocina_data = resp.get_json()
        check('API cocina responde', cocina_data is not None)

        pendientes = [o for o in cocina_data if o['estado_entrega'] == 'pendiente']
        listos = [o for o in cocina_data if o['estado_entrega'] == 'listo']
        check(f'Pedidos pendientes en cocina: {len(pendientes)} (Venta #4)', len(pendientes) == 1)
        check(f'Pedidos listos en cocina: {len(listos)} (Venta #2)', len(listos) == 1)

        # ============================================================
        print('\n' + '='*60)
        print('13. BUSCAR VENTAS')
        print('='*60)
        resp = client.get(f'/s/{codigo}/ventas/buscar?q=Pedro')
        busq = resp.get_json()
        check(f'Búsqueda "Pedro" → {len(busq)} resultado(s)', len(busq) == 1)
        check(f'  Resultado: orden #{busq[0]["numero_orden"]}, ${busq[0]["total_final"]:,}',
              busq[0]['numero_orden'] == 1 and busq[0]['total_final'] == 8000)

        resp = client.get(f'/s/{codigo}/ventas/buscar?q=3')
        busq = resp.get_json()
        check(f'Búsqueda "3" (orden #3) → encontrado', any(b['numero_orden'] == 3 for b in busq))

        # ============================================================
        print('\n' + '='*60)
        print('14. EXPORTAR EXCEL DE SESIÓN')
        print('='*60)
        resp = client.get(f'/s/{codigo}/sesiones/{sesion.id}/excel')
        check('Excel sesión → 200', resp.status_code == 200)
        check('Content-Type es xlsx', 'spreadsheet' in resp.content_type)

        from openpyxl import load_workbook
        wb = load_workbook(BytesIO(resp.data))
        check(f'Hojas: {wb.sheetnames}', len(wb.sheetnames) == 2)
        check('Hoja 1: "Detalle Ventas"', wb.sheetnames[0] == 'Detalle Ventas')
        check('Hoja 2: "Productos"', wb.sheetnames[1] == 'Productos')

        ws = wb['Detalle Ventas']
        # Check title
        titulo = ws['A1'].value
        check(f'Título Excel: "{titulo}"', 'Feria Test E2E' in titulo and 'Feria Prueba Completa' in titulo)

        # Find all data in the sheet
        all_values = []
        for row in ws.iter_rows(values_only=True):
            all_values.append(row)

        # Check financial summary
        flat = str(all_values)
        check('"Total Ventas" en resumen', 'Total Ventas' in flat)
        check('"Total Recaudado" en resumen', 'Total Recaudado' in flat)
        check('"Efectivo" en resumen', 'Efectivo' in flat)
        check('"Transferencia" en resumen', 'Transferencia' in flat)

        # Check ventas detail
        check('"Pedro Sánchez" en detalle', 'Pedro' in flat)
        check('"Luisa Martínez" en detalle', 'Luisa' in flat)
        check('"Roberto Díaz" en detalle', 'Roberto' in flat)
        check('"Sofía Vargas" en detalle', 'Sof' in flat)

        # Check products in detail
        check('"Empanada de Pino" en detalle', 'Empanada de Pino' in flat)
        check('"Choripán" en detalle', 'Chorip' in flat)
        check('"Jugo Natural" en detalle', 'Jugo Natural' in flat)

        # Check REMATE note appears
        check('"REMATE" en notas de Excel', 'REMATE' in flat)

        # Check payment/delivery status
        check('"Pagado" en estado de pago', 'Pagado' in flat)
        check('"Parcial" en estado de pago', 'Parcial' in flat)
        check('"Pendiente" en estado de pago', 'Pendiente' in flat)
        check('"Entregado" en estado de entrega', 'Entregado' in flat)

        # Check total general
        check('$35.000 (total general) en Excel', any(
            35000 in (row or ()) for row in all_values
        ))

        # Check Productos sheet
        ws2 = wb['Productos']
        prod_values = []
        for row in ws2.iter_rows(values_only=True):
            prod_values.append(row)
        flat2 = str(prod_values)
        check('"Empanada de Pino" en hoja Productos', 'Empanada de Pino' in flat2)
        check('"Choripán" en hoja Productos', 'Chorip' in flat2)
        check('"Jugo Natural" en hoja Productos', 'Jugo Natural' in flat2)
        check('"Cantidad Vendida" como columna', 'Cantidad Vendida' in flat2)
        check('"% del Total" como columna', '% del Total' in flat2)

        # ============================================================
        print('\n' + '='*60)
        print('15. EXPORTAR EXCEL COMPLETO (REGISTROS)')
        print('='*60)
        resp = client.get(f'/s/{codigo}/registros/exportar-todo')
        check('Excel completo → 200', resp.status_code == 200)
        wb2 = load_workbook(BytesIO(resp.data))
        ws_all = wb2.active
        check(f'Nombre hoja: "{ws_all.title}"', ws_all.title == 'Todas las Ventas')

        all_reg = []
        for row in ws_all.iter_rows(values_only=True):
            all_reg.append(row)
        flat_reg = str(all_reg)
        check('"Feria Test E2E" en título', 'Feria Test E2E' in flat_reg)
        check('4 ventas en Excel completo', flat_reg.count('Efectivo') + flat_reg.count('Transferencia') == 4)

        # ============================================================
        print('\n' + '='*60)
        print('16. EXPORTAR EXCEL DÍA')
        print('='*60)
        resp = client.get(f'/s/{codigo}/registros/{hoy}/excel')
        check('Excel día → 200', resp.status_code == 200)
        wb3 = load_workbook(BytesIO(resp.data))
        check(f'Hojas día: {wb3.sheetnames}', len(wb3.sheetnames) == 2)

        # ============================================================
        print('\n' + '='*60)
        print('17. VERIFICAR DASHBOARD')
        print('='*60)
        resp = client.get(f'/s/{codigo}')
        check('Dashboard → 200', resp.status_code == 200)
        html_dash = resp.data.decode('utf-8')
        check('"Feria Test E2E" en dashboard', 'Feria Test E2E' in html_dash)

        # ============================================================
        print('\n' + '='*60)
        print('18. VERIFICAR REGISTROS DEL DÍA')
        print('='*60)
        resp = client.get(f'/s/{codigo}/registros/{hoy}')
        check('Registro del día → 200', resp.status_code == 200)
        html_reg = resp.data.decode('utf-8')
        # Notas no se renderizan en la vista de registro del día (sí en Excel)
        check('Registro del día tiene ventas', '35.000' in html_reg or '35,000' in html_reg)

        # ============================================================
        print('\n' + '='*60)
        print('19. EDITAR VENTA (cambiar productos)')
        print('='*60)
        # Edit Venta 4: remove jugo, add choripán
        items_edit = json.dumps([
            {'producto_id': empanada.id, 'cantidad': 4, 'precio': 2500},
            {'producto_id': choripan.id, 'cantidad': 1, 'precio': 3000},
        ])
        # Empanada: 1 batch promo + 1 extra = $7500
        # Choripán: 1*$3000 = $3000
        # Total = $10.500
        resp = client.post(f'/s/{codigo}/ventas/{v4.id}/editar', data={
            'cliente_nombre': 'Sofía Vargas',
            'notas': 'Pedido editado',
            'total_final': '10500',
            'items': items_edit,
        }, follow_redirects=True)
        check('Editar venta #4 → 200', resp.status_code == 200)

        db.session.refresh(v4)
        detalles_v4 = v4.detalles
        nombres_v4 = [d.nombre_producto for d in detalles_v4]
        check(f'Venta #4 editada: productos = {nombres_v4}',
              'Empanada de Pino' in nombres_v4 and 'Choripán' in nombres_v4)
        check(f'  Jugo eliminado del pedido', 'Jugo Natural' not in nombres_v4)
        check(f'  notas: "{v4.notas}"', v4.notas == 'Pedido editado')

        # ============================================================
        print('\n' + '='*60)
        print('20. CERRAR SESIÓN')
        print('='*60)
        resp = client.post(f'/s/{codigo}/sesiones/{sesion.id}/estado', data={
            'estado': 'cerrada',
        }, follow_redirects=True)
        db.session.refresh(sesion)
        check(f'Sesión cerrada: estado={sesion.estado}', sesion.estado == 'cerrada')

        # ============================================================
        print('\n' + '='*60)
        print('21. VERIFICAR STOCK FINAL')
        print('='*60)
        resp = client.get(f'/s/{codigo}/stock')
        stock_final = resp.get_json()

        choripan_final = [s for s in stock_final if s['nombre'] == 'Choripán'][0]
        # Choripán: v1(1) + v3(3) + v4-editado(1) = 5, disponible = 20-5 = 15
        check(f'Choripán final: vendido={choripan_final["vendido"]}, disponible={choripan_final["disponible"]}',
              choripan_final['vendido'] == 5 and choripan_final['disponible'] == 15)

        jugo_final = [s for s in stock_final if s['nombre'] == 'Jugo Natural'][0]
        # Jugo: v3(4) + v4-editado(0, fue eliminado) = 4, disponible = 50-4 = 46
        check(f'Jugo final: vendido={jugo_final["vendido"]}, disponible={jugo_final["disponible"]}',
              jugo_final['vendido'] == 4 and jugo_final['disponible'] == 46)

        # ============================================================
        print('\n' + '='*60)
        print('22. VERIFICAR LISTA DE SESIONES')
        print('='*60)
        resp = client.get(f'/s/{codigo}/sesiones')
        check('Lista sesiones → 200', resp.status_code == 200)
        html_ses = resp.data.decode('utf-8')
        check('"Feria Prueba Completa" en lista', 'Feria Prueba Completa' in html_ses)
        check('"cerrada" badge en lista', 'cerrada' in html_ses.lower())

        # ============================================================
        print('\n' + '='*60)
        print('23. INVERSION POR SESION - AJAX')
        print('='*60)

        # Reabrir sesión para probar inversión
        resp = client.post(f'/s/{codigo}/sesiones/{sesion.id}/estado', data={
            'estado': 'abierta',
        }, follow_redirects=True)
        db.session.refresh(sesion)
        check(f'Sesión reabierta: estado={sesion.estado}', sesion.estado == 'abierta')

        # Verificar inversión inicial es 0
        check(f'Inversión inicial sesión: {sesion.inversion}', (sesion.inversion or 0) == 0)

        # --- Test AJAX: Setear inversión a $15.000 ---
        resp = client.post(f'/s/{codigo}/sesiones/{sesion.id}/inversion',
                           data={'inversion': '15000'},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
        check('AJAX inversión → 200', resp.status_code == 200)
        data = resp.get_json()
        check(f'JSON success=True', data.get('success') is True)
        check(f'JSON inversion=15000', data.get('inversion') == 15000)

        db.session.refresh(sesion)
        check(f'Inversión en DB: ${sesion.inversion:,}', sesion.inversion == 15000)

        # --- Test AJAX: Actualizar inversión a $25.000 ---
        resp = client.post(f'/s/{codigo}/sesiones/{sesion.id}/inversion',
                           data={'inversion': '25000'},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
        data = resp.get_json()
        check('Actualizar inversión a $25.000', data.get('success') is True and data.get('inversion') == 25000)
        db.session.refresh(sesion)
        check(f'Inversión actualizada en DB: ${sesion.inversion:,}', sesion.inversion == 25000)

        # --- Test AJAX: Inversión a $0 ---
        resp = client.post(f'/s/{codigo}/sesiones/{sesion.id}/inversion',
                           data={'inversion': '0'},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
        data = resp.get_json()
        check('Inversión a $0', data.get('success') is True and data.get('inversion') == 0)
        db.session.refresh(sesion)
        check(f'Inversión $0 en DB', sesion.inversion == 0)

        # --- Test AJAX: Valor invalido ---
        resp = client.post(f'/s/{codigo}/sesiones/{sesion.id}/inversion',
                           data={'inversion': 'abc'},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
        check('Valor invalido → 400', resp.status_code == 400)
        data = resp.get_json()
        check('JSON error en valor invalido', data.get('success') is False)

        # --- Test form POST (redirect) ---
        resp = client.post(f'/s/{codigo}/sesiones/{sesion.id}/inversion',
                           data={'inversion': '50000'},
                           follow_redirects=False)
        check('Form POST inversión → 302 redirect', resp.status_code == 302)
        db.session.refresh(sesion)
        check(f'Inversión via form: ${sesion.inversion:,}', sesion.inversion == 50000)

        # ============================================================
        print('\n' + '='*60)
        print('24. DASHBOARD CON INVERSION DE SESION')
        print('='*60)

        resp = client.get(f'/s/{codigo}')
        check('Dashboard con sesión activa → 200', resp.status_code == 200)
        html_dash = resp.data.decode('utf-8')

        # Verificar que muestra inversión de la sesión
        check('"Inversion" en dashboard', 'Inversion' in html_dash)
        check('"Editar Inversion Sesion" en dashboard', 'Editar Inversion Sesion' in html_dash)
        check('"Recaudado" en dashboard', 'Recaudado' in html_dash)
        check('"Ganancia" en dashboard', 'Ganancia' in html_dash)
        check('Input inversión presente', 'input-inversion' in html_dash)
        check('Boton guardar presente', 'btn-guardar-inv' in html_dash)
        check('Feedback element presente', 'inv-feedback' in html_dash)
        check('Auto-save JS presente', 'guardarInversion' in html_dash)
        check('Debounce JS presente', 'debounceTimer' in html_dash)

        # Verificar que la ganancia se calcula con inversión de sesión
        # total_recaudado actual = $35.000, inversión sesión = $50.000
        # ganancia = $35.000 - $50.000 = -$15.000
        check('Ganancia negativa (profit-negative) mostrada', 'profit-negative' in html_dash)
        check('$50,000 inversión en valor input', 'value="50000"' in html_dash)

        # Sin sesión: no debe haber HTML de error
        check('Sin error HTML en dashboard', 'Internal Server Error' not in html_dash)
        check('Sin error 500 en dashboard', 'Error interno' not in html_dash)

        # ============================================================
        print('\n' + '='*60)
        print('25. DETALLE SESION CON INVERSION')
        print('='*60)

        resp = client.get(f'/s/{codigo}/sesiones/{sesion.id}')
        check('Detalle sesión → 200', resp.status_code == 200)
        html_det = resp.data.decode('utf-8')

        check('"Inversion" en detalle sesión', 'Inversion' in html_det)
        check('"Ganancia" en detalle sesión', 'Ganancia' in html_det)
        check('"Editar Inversion" en detalle sesión', 'Editar Inversion' in html_det)
        check('Input inversión en detalle', 'ses-input-inversion' in html_det)
        check('Boton guardar en detalle', 'ses-btn-guardar-inv' in html_det)
        check('Auto-save JS en detalle', 'guardarInversion' in html_det)
        check('$50,000 inversión en detalle', 'value="50000"' in html_det)
        check('Sin error HTML en detalle', 'Internal Server Error' not in html_det)

        # ============================================================
        print('\n' + '='*60)
        print('26. DASHBOARD SIN SESION ACTIVA')
        print('='*60)

        # Cerrar sesión
        resp = client.post(f'/s/{codigo}/sesiones/{sesion.id}/estado', data={
            'estado': 'cerrada',
        }, follow_redirects=True)
        db.session.refresh(sesion)
        check(f'Sesión cerrada: {sesion.estado}', sesion.estado == 'cerrada')

        resp = client.get(f'/s/{codigo}')
        check('Dashboard sin sesión → 200', resp.status_code == 200)
        html_noact = resp.data.decode('utf-8')
        check('"Abre una sesion" mensaje', 'Abre una sesion' in html_noact)
        check('Sin input inversión (no hay sesión)', 'input-inversion' not in html_noact)
        check('Sin error HTML', 'Internal Server Error' not in html_noact)

        # ============================================================
        print('\n' + '='*60)
        print('27. INVERSION INDEPENDIENTE POR SESION')
        print('='*60)

        # Crear segunda sesión y verificar que tiene inversión independiente
        resp = client.post(f'/s/{codigo}/sesiones/nueva', data={
            'fecha': hoy,
            'nombre': 'Segunda Sesion',
        }, follow_redirects=False)
        check('Segunda sesión creada', resp.status_code == 302)

        sesion2 = SesionVenta.query.filter_by(stand_id=stand.id, nombre='Segunda Sesion').first()
        check(f'Segunda sesión en DB', sesion2 is not None)
        check(f'Inversión inicial sesión 2: {sesion2.inversion or 0}', (sesion2.inversion or 0) == 0)

        # Setear inversión en segunda sesión
        resp = client.post(f'/s/{codigo}/sesiones/{sesion2.id}/inversion',
                           data={'inversion': '80000'},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
        data = resp.get_json()
        check('Inversión sesión 2 = $80.000', data.get('success') is True)

        # Verificar que sesión 1 mantiene su inversión
        db.session.refresh(sesion)
        db.session.refresh(sesion2)
        check(f'Sesión 1 mantiene inversión: ${sesion.inversion:,}', sesion.inversion == 50000)
        check(f'Sesión 2 tiene inversión: ${sesion2.inversion:,}', sesion2.inversion == 80000)

        # ============================================================
        print('\n' + '='*60)
        print('28. DETALLE SESION CERRADA CON INVERSION')
        print('='*60)

        # La sesión 1 está cerrada con inversión $50.000
        resp = client.get(f'/s/{codigo}/sesiones/{sesion.id}')
        check('Detalle sesión cerrada → 200', resp.status_code == 200)
        html_cerrada = resp.data.decode('utf-8')
        check('Inversión visible en sesión cerrada', 'Inversion' in html_cerrada)
        check('Ganancia visible en sesión cerrada', 'Ganancia' in html_cerrada)
        check('Sin error HTML', 'Internal Server Error' not in html_cerrada)
        check('Sin error 500', 'Error interno' not in html_cerrada)

        # ============================================================
        print('\n' + '='*60)
        print('29. TODAS LAS PAGINAS SIN ERRORES')
        print('='*60)

        pages = [
            (f'/s/{codigo}', 'Dashboard'),
            (f'/s/{codigo}/sesiones', 'Lista sesiones'),
            (f'/s/{codigo}/sesiones/{sesion.id}', 'Detalle sesión 1'),
            (f'/s/{codigo}/sesiones/{sesion2.id}', 'Detalle sesión 2'),
            (f'/s/{codigo}/productos', 'Productos'),
            (f'/s/{codigo}/promociones', 'Promociones'),
            (f'/s/{codigo}/integrantes', 'Integrantes'),
            (f'/s/{codigo}/registros', 'Registros'),
            (f'/s/{codigo}/registros/{hoy}', f'Registro día {hoy}'),
            (f'/s/{codigo}/cocina', 'Cocina'),
        ]

        for url, name in pages:
            resp = client.get(url)
            html_page = resp.data.decode('utf-8')
            is_ok = resp.status_code == 200
            no_error = 'Internal Server Error' not in html_page and 'Traceback' not in html_page
            check(f'{name} → {resp.status_code}, sin errores', is_ok and no_error,
                  f'status={resp.status_code}' if not is_ok else 'contiene error HTML' if not no_error else '')

        # ============================================================
        # CLEANUP
        os.unlink(TEST_DB)

    # ============================================================
    print('\n' + '='*60)
    total = len(errors)
    if total == 0:
        print(f'\n  {PASS}  TODOS LOS TESTS PASARON')
    else:
        print(f'\n  {FAIL}  {total} test(s) fallaron:')
        for e in errors:
            print(f'    - {e}')
    print('='*60 + '\n')
    return 0 if total == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
