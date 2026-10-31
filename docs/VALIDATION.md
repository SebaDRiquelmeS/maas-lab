# Validación y límites

## Qué se observó en el laboratorio de origen

Omarchy x86_64, Ryzen 5 5600H, 22 GiB RAM, QEMU/KVM y libvirt. Se creó el controlador Ubuntu 24.04, MAAS 3.7.4 y PostgreSQL 16.15; se verificó HTTP 200, API autenticada, DHCP, imagen completa y commissioning aprobado. El usuario desplegó Ubuntu desde la UI y confirmó que funcionaba. VirtualBMC 3.4.0 se conectó a MAAS por IPMI y devolvió estado `on`.

Esas observaciones corresponden al montaje original, no a una ejecución nueva y completa de todos los scripts de este repositorio. Los scripts se reescribieron para eliminar rutas, IDs y credenciales particulares.

## Comprobaciones del repositorio

- Compilación/sintaxis Python y Bash.
- Pruebas unitarias de validación de configuración, detección de solapamientos de red, negativa a adoptar redes ajenas, protección del estado y verificación de imagen incompleta.
- Revisión de archivos incluidos en Git para excluir secretos y artefactos de ejecución.
- CI de comprobaciones estáticas y unitarias, sin privilegios ni creación de VM.

## Pendiente de validar en equipos adicionales

Ejecutar toda la secuencia desde un Ubuntu 24.04 limpio; repetir sobre Arch/Omarchy actualizado; verificar apagado/encendido y bootdev IPMI durante commissioning y deploy automáticos; probar recuperación de cortes de red e instalaciones interrumpidas. Las pruebas con mocks no reemplazan esas comprobaciones.

## Matriz manual de aceptación

1. Equipo limpio: bootstrap y doctor terminan sin error.
2. Controller: arranca, obtiene DHCP en NAT y dirección estática privada.
3. Firewall: conserva la política del equipo y permite únicamente los flujos descritos.
4. MAAS: UI HTTP responde, administrador accede, PostgreSQL y NTP activos.
5. Configure: DHCP solo en provisioning; imagen noble completa.
6. Node: PXE correcto, registro New, primer arranque termina.
7. BMC: consulta IPMI coincide con virsh; no hay escucha IPMI sobre LAN.
8. UI: Commission termina Ready y detecta recursos/disco.
9. UI: Deploy termina Deployed sin reinicio manual.
10. SSH al nodo confirma Ubuntu noble y disco persistente.
11. Reinicio del anfitrión: redes y BMC vuelven a estar disponibles; arrancar el controlador manualmente si no está encendido.
12. Cleanup deliberado solo elimina recursos del prefijo elegido.

No se habilita autostart de las VM: evita reservar 10 GiB de RAM sin que el usuario decida. Las redes y el BMC sí se habilitan como servicios persistentes.
