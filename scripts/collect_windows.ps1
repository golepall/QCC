# QCC 测试报告自动化 - Windows 系统信息采集脚本
# 用法: powershell -ExecutionPolicy Bypass -File collect_windows.ps1 -OutputPath "D:\config.json"

param(
    [string]$OutputPath = ".\system_config_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  QCC 系统信息自动采集工具" -ForegroundColor Cyan
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$config = @{
    source       = "windows_script"
    collect_time = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    hostname     = $env:COMPUTERNAME
}

Write-Host "[1/12] 采集 BIOS 信息..." -ForegroundColor Yellow
$bios = Get-WmiObject Win32_BIOS
$config.bios_vendor  = $bios.Manufacturer
$config.bios_version = $bios.SMBIOSBIOSVersion
$config.bios_date    = if ($bios.ReleaseDate) {
    [Management.ManagementDateTimeConverter]::ToDateTime($bios.ReleaseDate).ToString("yyyy-MM-dd")
} else { "" }

$ec = Get-WmiObject Win32_BIOS | Select-Object -ExpandProperty BIOSVersion -ErrorAction SilentlyContinue
$config.ec_version = ""

Write-Host "[2/12] 采集 CPU 信息..." -ForegroundColor Yellow
$cpu = Get-WmiObject Win32_Processor
$config.cpu_model     = $cpu.Name.Trim()
$config.cpu_frequency = [string]$cpu.MaxClockSpeed
$config.cpu_cores     = $cpu.NumberOfCores

Write-Host "[3/12] 采集内存信息..." -ForegroundColor Yellow
$memModules = Get-WmiObject Win32_PhysicalMemory
$config.memory_info = @()
foreach ($mem in $memModules) {
    $config.memory_info += @{
        vendor   = $mem.Manufacturer
        model    = $mem.PartNumber.Trim()
        capacity = [string]([math]::Round($mem.Capacity / 1MB))
        frequency = [string]$mem.Speed
        slot     = $mem.DeviceLocator
    }
}

Write-Host "[4/12] 采集硬盘信息..." -ForegroundColor Yellow
$disks = Get-PhysicalDisk
$config.disk_info = @()
foreach ($disk in $disks) {
    $config.disk_info += @{
        vendor    = $disk.Manufacturer
        model     = $disk.FriendlyName
        capacity  = [string]$disk.Size
        interface = $disk.BusType
        mediaType = $disk.MediaType
    }
}

Write-Host "[5/12] 采集显卡信息..." -ForegroundColor Yellow
$gpus = Get-CimInstance Win32_VideoController
$gpuList = @()
foreach ($gpu in $gpus) {
    $gpuList += "$($gpu.Name)"
}
$config.gpu_model  = $gpus | Select-Object -First 1 -ExpandProperty Name
$config.gpu_driver = $gpus | Select-Object -First 1 -ExpandProperty DriverVersion

Write-Host "[6/12] 采集显示器信息..." -ForegroundColor Yellow
$monitors = Get-CimInstance WmiMonitorID -Namespace root\wmi -ErrorAction SilentlyContinue
if ($monitors) {
    $m = $monitors | Select-Object -First 1
    $manufacturer = ($m.ManufacturerName | Where-Object {$_ -ne 0} | ForEach-Object {[char]$_}) -join ''
    $product = ($m.ProductCodeID | Where-Object {$_ -ne 0} | ForEach-Object {[char]$_}) -join ''
    $config.panel_info = "$manufacturer $product".Trim()
}
$desktop = Get-CimInstance Win32_DesktopMonitor | Select-Object -First 1
$config.panel_resolution = ""

Write-Host "[7/12] 采集网络适配器信息..." -ForegroundColor Yellow
$wifi = Get-NetAdapter | Where-Object { $_.InterfaceDescription -match 'Wi-Fi|Wireless|WLAN' } | Select-Object -First 1
if ($wifi) {
    $config.wlan_model  = $wifi.InterfaceDescription
    $config.wlan_driver = $wifi.DriverVersionString
}

$ethernet = Get-NetAdapter | Where-Object { $_.InterfaceDescription -match 'Ethernet|LAN|Realtek.*GbE|Intel.*Ethernet' -and $_.InterfaceDescription -notmatch 'Wi-Fi|Wireless|Bluetooth' } | Select-Object -First 1
if ($ethernet) {
    $config.lan_model  = $ethernet.InterfaceDescription
    $config.lan_driver = $ethernet.DriverVersionString
}

Write-Host "[8/12] 采集蓝牙信息..." -ForegroundColor Yellow
$bt = Get-PnpDevice | Where-Object { $_.FriendlyName -match 'Bluetooth' -and $_.Status -eq 'OK' } | Select-Object -First 1
if ($bt) {
    $config.bt_model = $bt.FriendlyName
}

Write-Host "[9/12] 采集声卡信息..." -ForegroundColor Yellow
$audio = Get-CimInstance Win32_SoundDevice | Select-Object -First 1
if ($audio) {
    $config.audio_codec  = $audio.Name
    $config.audio_driver = $audio.DriverVersion
}

Write-Host "[10/12] 采集摄像头信息..." -ForegroundColor Yellow
$camera = Get-PnpDevice | Where-Object { $_.FriendlyName -match 'Camera|Webcam|相机|摄像头' -and $_.Status -eq 'OK' } | Select-Object -First 1
if ($camera) {
    $config.camera_model = $camera.FriendlyName
}

Write-Host "[11/12] 采集触摸板信息..." -ForegroundColor Yellow
$touchpad = Get-CimInstance Win32_PointingDevice | Where-Object { $_.Name -notmatch 'Mouse|鼠标' } | Select-Object -First 1
if ($touchpad) {
    $config.touchpad_model  = $touchpad.Name
    $config.touchpad_driver = $touchpad.DriverVersion
}

Write-Host "[12/12] 采集操作系统信息..." -ForegroundColor Yellow
$os = Get-ComputerInfo
$config.os_version  = $os.OsVersion
$config.os_build    = $os.WindowsBuildLabEx
$config.os_language  = $os.OsLanguage
$config.os_kernel   = (Get-WmiObject Win32_OperatingSystem).Version

$battery = Get-WmiObject Win32_Battery
if ($battery) {
    $config.battery_info = "$($battery.Name) $($battery.DesignCapacity)mAh"
}
$config.adapter_info = ""

$allPnp = Get-PnpDevice | Where-Object { $_.Status -eq 'OK' }
$fingerprint = $allPnp | Where-Object { $_.FriendlyName -match 'Fingerprint|指纹' } | Select-Object -First 1
if ($fingerprint) { $config.fingerprint_model = $fingerprint.FriendlyName }

$cardreader = $allPnp | Where-Object { $_.FriendlyName -match 'Card|Reader|读卡' -and $_.Class -match 'USB' } | Select-Object -First 1
if ($cardreader) { $config.cardreader_model = $cardreader.FriendlyName }

$config.motherboard = (Get-WmiObject Win32_BaseBoard).Product

$json = $config | ConvertTo-Json -Depth 5
$json | Out-File -FilePath $OutputPath -Encoding UTF8

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  采集完成！" -ForegroundColor Green
Write-Host "  输出文件: $OutputPath" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "采集结果摘要:" -ForegroundColor Cyan
Write-Host "  CPU:    $($config.cpu_model)"
Write-Host "  内存:   $(($config.memory_info | ForEach-Object { "$($_.capacity)MB" }) -join ', ')"
Write-Host "  硬盘:   $(($config.disk_info | ForEach-Object { "$($_.model) $($_.capacity)" }) -join ', ')"
Write-Host "  显卡:   $($config.gpu_model)"
Write-Host "  网卡:   LAN=$($config.lan_model), WLAN=$($config.wlan_model)"
Write-Host "  OS:     $($config.os_version)"
Write-Host ""
