# Driver matching

The Drivers page reads currently present PnP devices and joins them to installed signed-driver metadata. It returns only the model/hardware portion of device IDs, not unique instance suffixes. Physical device buses and virtual-device exclusions keep disconnected and software adapters out of the results. Unknown physical devices can still appear without an installed version.

The NVIDIA, AMD and Intel installer panels remain hidden until corresponding hardware is detected. OEM support URLs and the underlying component vendor are tracked separately so, for example, an Intel Wi-Fi card in an AMD PC can still enable Intel support. Refresh rechecks presence and removes absent matches.

Audio, Bluetooth, network, storage, USB, input, camera, monitor, chipset and other present hardware receive installed-driver information plus applicable Windows Update and official support controls. RAM and other hardware without a separate Windows driver do not receive invented downloads. Firmware/BIOS links require exact-model selection at the manufacturer. Only validated supported vendor installers download directly; Windows Update installs only updates selected by the user.

Official API references: [Get-PnpDevice -PresentOnly](https://learn.microsoft.com/en-us/powershell/module/pnpdevice/get-pnpdevice) and [Windows Update Agent](https://learn.microsoft.com/en-us/windows/win32/api/_wua/).
