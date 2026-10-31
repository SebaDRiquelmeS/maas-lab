# Diagnóstico

Los ejemplos usan el prefijo `ml`. Adáptalos si elegiste otro. Lee el mensaje completo de error antes de repetir pasos.

## No existe /dev/kvm

Activa SVM/AMD-V o Intel VT-x en BIOS/UEFI y reinicia. En una VM anfitriona comprueba que el hipervisor permita virtualización anidada. `sudo modprobe kvm_amd` o `sudo modprobe kvm_intel` puede indicar si el kernel encuentra soporte. No uses emulación lenta como sustituto silencioso de KVM.

## No conecta con libvirt

```bash
sudo systemctl status libvirtd
sudo virsh -c qemu:///system list --all
```

Usa `qemu:///system`, no `qemu:///session`. En Arch, una actualización de kernel pendiente de reinicio puede impedir cargar módulos. Si tu distribución configura demonios modulares de libvirt, adapta el servicio al de QEMU/red; el bootstrap soporta la instalación monolítica descrita.

## SSH no responde en el controlador

```bash
sudo virsh -c qemu:///system domstate ml-controller
sudo virsh -c qemu:///system net-dhcp-leases ml-nat
sudo python3 lab.py firewall
virt-manager --connect qemu:///system --show-domain-console ml-controller
```

Espera el primer arranque. `Connection refused` suele indicar que SSH aún no arrancó; un timeout puede indicar red/cortafuegos. `systemd-networkd-wait-online` esperando y ausencia de concesión DHCP suelen apuntar al cortafuegos. No desactives UFW completo: comprueba las reglas y las redes.

## Error de descarga o checksum

El script descarga por HTTPS y compara SHA-256 con el manifiesto del mismo origen. La URL `current` es mutable; si cambia entre las dos descargas, elimina solo `/var/lib/maas-lab/ml/ubuntu.img` y `SHA256SUMS`, y vuelve a intentar antes de crear la VM. Nunca omitas la comprobación. No borres el disco `controller.qcow2` de un controlador ya creado.

## MAAS o PostgreSQL no terminan de instalarse

```bash
sudo python3 lab.py ssh
# Dentro de la VM, usando la sesión SSH interactiva del README:
sudo snap changes
sudo snap tasks ID_DEL_CAMBIO
sudo snap services
sudo maas status
```

Un reinicio automático de snapd en su primera instalación puede ser normal. Si interrumpiste las migraciones, inspecciona la base y los logs antes de repetir. `guest-init.py` reutiliza rol/base/administrador si existen, pero no repara cualquier migración incompleta. Conserva `/root/lab-credentials.json` de la VM.

## La imagen existe pero el nodo no arranca

En **Images** comprueba que Ubuntu noble amd64 con kernel GA terminó de sincronizarse. El script `node` exige un conjunto con `complete: true`. Consulta los eventos del controlador y la salida de `sudo maas status` dentro de la VM.

## Node creado en MAAS pero falló virt-install

El registro y la creación de VM no son atómicos. El script guarda `node.json` al registrar el nodo; si falla la creación del disco/VM, inspecciona primero `virsh list --all`, MAAS y el directorio de discos. Conserva el ID registrado. El comando reutiliza el registro guardado al reintentar; si quedó un disco parcial sin VM, decide expresamente si debe conservarse o eliminarse. No borres un nodo ya desplegado como forma de reintentar.

## Commissioning tarda demasiado

Mira **Machines → nodo → Events** y la consola gráfica. El primer arranque de registro suele apagarse antes del commissioning. Espera a que termine; después configura BMC y ordena Commission. La inspección de hardware y las pruebas pueden tardar varios minutos. No despliegues mientras el nodo siga en Commissioning.

## Deploying pero conserva la pantalla anterior

Comprueba que la potencia esté configurada como IPMI y que la consulta de estado funcione. Si figura Manual, MAAS no puede reiniciar la VM. No pulses reinicio repetidamente durante una instalación activa: revisa los eventos para distinguir una tarea esperando encendido de una instalación que ya está escribiendo el disco.

## BMC no responde

```bash
sudo systemctl status maas-lab-ml-bmc.service
sudo journalctl -u maas-lab-ml-bmc.service -n 80 --no-pager
sudo virsh -c qemu:///system net-list --all
sudo ss -lun | grep 16230
sudo python3 lab.py firewall
```

El BMC debe escuchar en `192.168.211.1:16230`, no en la IP del nodo. La dirección `.1` existe cuando el puente está activo. MAAS usa IPMI 2.0 con cipher **3**: algunas combinaciones de clientes pyghmi pueden negociar un cipher incompatible; comprueba con la consulta de estado de MAAS. El puerto local 50892 no debe estar ocupado por otro vbmcd.

El servicio no puede encender el portátil ni funcionar con el anfitrión apagado. Si MAAS consulta un estado obsoleto, vuelve a consultar tras unos segundos.

## Consola serie en blanco

La VM puede funcionar y no emitir mensajes por serie. Abre la consola gráfica de virt-manager. Para salir de `virsh console`, usa **Ctrl + ]**. No hay contraseña genérica del usuario Ubuntu; utiliza SSH con la clave del laboratorio.

## SSH advierte que cambió la clave del nodo

Puede ocurrir después de reinstalar Ubuntu. Comprueba primero en MAAS y la consola que estás contactando el nodo correcto. Solo entonces elimina esa entrada concreta del known_hosts del laboratorio; no desactives la comprobación de claves globalmente.

## Qué adjuntar al reportar un problema

Distribución/versión, arquitectura, etapa ejecutada, mensaje de error, `virsh list --all`, estado de MAAS y eventos relevantes. No adjuntes tokens, claves privadas, `credentials.json`, `bmc-credentials.json` ni directorios de estado.
