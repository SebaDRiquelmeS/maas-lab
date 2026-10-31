# Red del laboratorio

## Dos redes con funciones diferentes

La red NAT (`ml-nat`, puente `vb-ml`) ofrece Internet al controlador mediante la conexión del anfitrión. libvirt ofrece DHCP en esa red. MAAS no debe prestar DHCP allí.

La red aislada (`ml-provision`, puente `vp-ml`) conecta controlador y nodo. No tiene DHCP de libvirt ni reenvío hacia la LAN. MAAS entrega IP, DNS y PXE. El anfitrión puede contactar las VM por sus IP privadas sin conectar el laboratorio a tu router.

Las MAC de ejemplo son fijas para el primer laboratorio. No ejecutes dos laboratorios con esas MAC conectados a la misma red.

## Qué modifica `firewall`

Solo si UFW devuelve `Status: active`:

- Entrada UDP 67 en `vb-ml`: solicitudes DHCP al dnsmasq de libvirt.
- Entrada UDP/TCP 53 en `vb-ml`: DNS de libvirt.
- Reenvío desde `192.168.210.0/24` entrando por `vb-ml` y saliendo por cada interfaz que actualmente tenga ruta predeterminada.
- Entrada UDP 16230 por `vp-ml`, desde `192.168.211.2` a `192.168.211.1`: BMC.

No cambia el acceso SSH del anfitrión, no abre IPMI en tu Ethernet/Wi-Fi y no desactiva el cortafuegos. Las reglas son persistentes. Si cambias de conexión y la interfaz de salida no estaba presente, repite `firewall`.

Con firewalld, nftables propio, VPN o políticas de red adicionales, el comando avisa pero no inventa reglas equivalentes. Autoriza el mismo tráfico y asegúrate de que el forwarding de la red NAT no esté bloqueado. Consulta la documentación de tu distribución y [libvirt](https://libvirt.org/firewall.html). El soporte automático de este repositorio se limita a UFW.

## Salida a Internet del nodo

El controlador usa NAT. El nodo usa una red aislada y no recibe una puerta de enlace por defecto. MAAS puede proporcionar su proxy de paquetes durante la instalación; eso no convierte la red en una conexión de Internet general.

Para añadir Internet al nodo después de la práctica necesitarías un router/NAT entre redes o una interfaz adicional configurada deliberadamente. Ese cambio no lo hace este proyecto: mantener el despliegue aislado evita interferir con el DHCP del hogar o de una oficina.

## Evitar interferencia de DHCP

No conectes el puente de provisioning a una tarjeta física. No actives MAAS DHCP en tu red LAN, en la red NAT o en una VLAN compartida con el router. Antes de pulsar Commission confirma en Subnets que MAAS presta DHCP solo en la subred elegida.

## Servicios y puertos

| Origen → destino | Puerto | Uso |
| --- | --- | --- |
| Navegador del anfitrión → controlador | TCP 5240 | MAAS web/API |
| Anfitrión → controlador/nodo | TCP 22 | SSH con clave |
| Nodo → controlador | UDP 67/68, 69 | DHCP / TFTP de arranque |
| Nodo → controlador | TCP 5240/5248 y puertos gestionados por MAAS | API, metadatos y recursos |
| Nodo → controlador | TCP/UDP 53 | DNS |
| Controlador → anfitrión privado | UDP 16230 | IPMI del nodo |
| Herramienta vbmc → vbmcd local | TCP 50892 en loopback | Gestión local del emulador |

Estos son los principales puertos del laboratorio, no una lista universal para producción. No publiques ni redirijas estos puertos desde tu router.
