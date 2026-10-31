# Eliminar el laboratorio deliberadamente

Estos comandos son **destructivos**: pierdes el Ubuntu del nodo, el controlador, su base y sus credenciales. No los uses para diagnosticar un error. Guarda antes lo que necesites. El proyecto no ejecuta esta secuencia automáticamente.

Usan el prefijo predeterminado `ml`. Comprueba los nombres con `sudo virsh -c qemu:///system list --all` antes de continuar.

1. Detén y deshabilita el BMC:

   ```bash
   sudo systemctl disable --now maas-lab-ml-bmc.service
   sudo rm /etc/systemd/system/maas-lab-ml-bmc.service
   sudo systemctl daemon-reload
   ```

2. Apaga los invitados desde sus sistemas o con `virsh shutdown`. Espera a que `domstate` indique apagado:

   ```bash
   sudo virsh -c qemu:///system shutdown ml-node01
   sudo virsh -c qemu:///system shutdown ml-controller
   ```

   Si alguno no existe o ya estaba apagado, su error es esperable. `destroy` fuerza el corte de energía y solo debe utilizarse si asumes la pérdida de escrituras pendientes.

3. Elimina la definición de cada VM apagada:

   ```bash
   sudo virsh -c qemu:///system undefine ml-node01
   sudo virsh -c qemu:///system undefine ml-controller
   ```

4. Elimina exclusivamente las redes del proyecto:

   ```bash
   sudo virsh -c qemu:///system net-destroy ml-provision
   sudo virsh -c qemu:///system net-undefine ml-provision
   sudo virsh -c qemu:///system net-destroy ml-nat
   sudo virsh -c qemu:///system net-undefine ml-nat
   ```

5. Inspecciona y elimina los archivos privados y discos del laboratorio si ya no necesitas recuperarlos:

   ```bash
   sudo ls -la /var/lib/libvirt/images/maas-lab-ml/
   sudo ls -la /var/lib/maas-lab/ml/
   sudo rm -r -- /var/lib/libvirt/images/maas-lab-ml/
   sudo rm -r -- /var/lib/maas-lab/ml/
   ```

6. Si ejecutaste `firewall`, revisa `sudo ufw status numbered` y elimina **solo** las reglas con `vb-ml`, `vp-ml` y la subred NAT elegida, usando `sudo ufw delete NUMERO`. Borra por número descendente y vuelve a revisar la lista, porque los índices cambian.

No elimines las redes `default`, los discos de otras VM ni paquetes del sistema que otros laboratorios puedan utilizar. No toques el laboratorio original con nombres `maas-controller` y `maas-node01` si convive con este.
