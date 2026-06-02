#!/usr/bin/env python3
"""Download popular app icons from arkahna/intune-icons and map to process names.

Usage:
    python tools/download_icons.py
"""

import json
import os
import sys
import urllib.request

# ── Mapping: intune-icons filename (without .png) → process_name ────
# Generated from the arkahna/intune-icons repo.
# Add entries here as needed — the downloader will fetch the icon and
# save it as <process_name>.png.

ICON_TO_PROCESS: dict[str, str] = {
    "1Password": "1password.exe",
    "7-Zip": "7zfm.exe",
    "Adobe-AcrobatReader": "acrord32.exe",
    "Audacity": "audacity.exe",
    "Brave": "brave.exe",
    "Fork": "fork.exe",
    "FoxitReader": "foxitreader.exe",
    "Gimp": "gimp.exe",
    "GitForWindows": "git.exe",
    "GitHub-Desktop": "github desktop.exe",
    "Google-AndroidStudio": "studio64.exe",
    "Google-Chrome": "chrome.exe",
    "Greenshot": "greenshot.exe",
    "HandBrake": "handbrake.exe",
    "Hyper": "hyper.exe",
    "ImageGlass": "imageglass.exe",
    "Krisp": "krisp.exe",
    "Microsoft-AzureDataStudio": "azuredatastudio.exe",
    "Microsoft-Edge": "msedge.exe",
    "Microsoft-EdgeWebView2Runtime": "msedgewebview2.exe",
    "Microsoft-Excel": "excel.exe",
    "Microsoft-FileExplorer": "explorer.exe",
    "Microsoft-Office": "msoffice.exe",
    "Microsoft-OneDrive": "onedrive.exe",
    "Microsoft-OneNote": "onenote.exe",
    "Microsoft-Outlook": "outlook.exe",
    "Microsoft-PowerPoint": "powerpnt.exe",
    "Microsoft-PowerShellCore": "pwsh.exe",
    "Microsoft-PowerToys": "powertoys.exe",
    "Microsoft-RemoteDesktop": "msrdc.exe",
    "Microsoft-RemoteDesktop2": "mstsc.exe",
    "Microsoft-SSMS": "ssms.exe",
    "Microsoft-Teams": "teams.exe",
    "Microsoft-ToDo": "todo.exe",
    "Microsoft-VSCode": "code.exe",
    "Microsoft-Visio": "visio.exe",
    "Microsoft-VisualStudio": "devenv.exe",
    "Microsoft-VisualStudioCode": "code.exe",
    "Microsoft-Whiteboard": "whiteboard.exe",
    "Microsoft-WindowsTerminal": "windowsterminal.exe",
    "Microsoft-Word": "winword.exe",
    "Microsoft365": "office365.exe",
    "MicrosoftSkypeForBusiness": "skype.exe",
    "MicrosoftStore-DevToys": "devtoys.exe",
    "MicrosoftStore-MSNWeather": "msnweather.exe",
    "MicrosoftStore-MicrosoftClipchamp": "clipchamp.exe",
    "MicrosoftStore-MicrosoftPhotos": "photos.exe",
    "MicrosoftStore-MicrosoftToDo": "todo.exe",
    "MicrosoftStore-Paint": "mspaint.exe",
    "MicrosoftStore-PhoneLink": "phonelink.exe",
    "MicrosoftStore-QuickAssist": "quickassist.exe",
    "MicrosoftStore-SnippingTool": "snippingtool.exe",
    "MicrosoftStore-Spotify-MusicandPodcasts": "spotify.exe",
    "MicrosoftStore-VLCUWP": "vlc.exe",
    "MicrosoftStore-WhatsApp": "whatsapp.exe",
    "MicrosoftStore-WindowsCalculator": "calculator.exe",
    "MicrosoftStore-WindowsMediaPlayer": "wmplayer.exe",
    "MicrosoftStore-WindowsNotepad": "notepad.exe",
    "MicrosoftStore-WindowsTerminal": "windowsterminal.exe",
    "MicrosoftStore-XboxGameBar": "xboxgamebar.exe",
    "Mozilla-Firefox": "firefox.exe",
    "NotepadPP": "notepad++.exe",
    "Paint.Net": "paintdotnet.exe",
    "PeaZip": "peazip.exe",
    "Signal": "signal.exe",
    "Slack": "slack.exe",
    "Speedtest": "speedtest.exe",
    "Spotify": "spotify.exe",
    "TeamViewer": "teamviewer.exe",
    "TechSmith-Camtasia": "camtasia.exe",
    "TechSmith-Snagit": "snagit.exe",
    "Telegram": "telegram.exe",
    "Telerick-FiddlerEverywhere": "fiddler everywhere.exe",
    "VLC": "vlc.exe",
    "Whatsapp": "whatsapp.exe",
    "WinZip": "winzip.exe",
    "Xmind": "xmind.exe",
    "Zoom": "zoom.exe",
    "Citrix-WorkspaceApp": "citrixworkspace.exe",
    "Dropbox": "dropbox.exe",
    "Sophos": "sophos.exe",
    "Bluejeans": "bluejeans.exe",
    "Cisco-WebEx": "webex.exe",
    "ConnectWise-Control": "connectwisecontrol.exe",
    "Termius": "termius.exe",
    "Lenovo-Vantage": "lenovovantage.exe",
    # ── Additional mappings (batch 2) ──
    "Adobe-AcrobatReader2": "acrobat.exe",
    "Apple-Mail": "mail.exe",
    "Apple-Safari": "safari.exe",
    "Apple-iTunes": "itunes.exe",
    "Apple-MobileDeviceSupport": "applemobiledevice.exe",
    "Citrix-Files": "citrixfiles.exe",
    "Citrix-Reciever": "citrixreceiver.exe",
    "Citrix-SSO": "citrixsso.exe",
    "Citrix-SecureHub": "citrixsecurehub.exe",
    "Citrix-SecureMail": "citrixsecuremail.exe",
    "Citrix-SecureWeb": "citrixsecureweb.exe",
    "Citrix-ShareFile": "citrixsharefile.exe",
    "Citrix-WorkflowsXenMobile": "citrixworkflows.exe",
    "Citrix-WorkspaceApp2": "citrixworkspaceapp.exe",
    "ConnectWise-Manage": "connectwisemanage.exe",
    "Dropbox-Metro": "dropbox.exe",
    "Freshservice-Agent": "freshservice.exe",
    "GitHub-Desktop2": "github desktop.exe",
    "Google-Chrome-macOS": "chrome.exe",
    "ImageOptim": "imageoptim.exe",
    "Iterate-Cyberduck1": "cyberduck.exe",
    "Iterate-Cyberduck2": "cyberduck.exe",
    "LaserficheConnector": "laserfiche.exe",
    "Lenovo": "lenovo.exe",
    "Logi-Options": "logioptions.exe",
    "Microsoft-Authenticator": "authenticator.exe",
    "Microsoft-Azure": "azure.exe",
    "Microsoft-AzureInformationProtection": "azureinfoprotection.exe",
    "Microsoft-AzurePipelines": "azurepipelines.exe",
    "Microsoft-Bookings": "microsoftbookings.exe",
    "Microsoft-Defender": "defender.exe",
    "Microsoft-Delve": "delve.exe",
    "Microsoft-Dynamics365": "dynamics365.exe",
    "Microsoft-DynamicsCRM": "dynamicscrm.exe",
    "Microsoft-DynamicsNAV": "dynamicsnav.exe",
    "Microsoft-Edge-Beta": "msedge.exe",
    "Microsoft-Edge-Dev": "msedge.exe",
    "Microsoft-FileExplorer-Old": "explorer.exe",
    "Microsoft-Flow": "microsoftflow.exe",
    "Microsoft-Games": "microsoftgames.exe",
    "Microsoft-GlobalSecureAccessClient": "globalsecureaccess.exe",
    "Microsoft-IntuneCompanyPortal": "companyportal.exe",
    "Microsoft-Kaizala": "kaizala.exe",
    "Microsoft-ManagedBrowser": "managedbrowser.exe",
    "Microsoft-MouseKeyboardCenter": "mousekeyboard.exe",
    "Microsoft-MyApps": "myapps.exe",
    "Microsoft-NET": "dotnet.exe",
    "Microsoft-Office-Lens": "officelens.exe",
    "Microsoft-OfficeDelve": "delve.exe",
    "Microsoft-OneNote-Metro": "onenote.exe",
    "Microsoft-Planner": "planner.exe",
    "Microsoft-PowerAutomateDesktop": "powerautomate.exe",
    "Microsoft-PowerBI": "powerbi.exe",
    "Microsoft-PowerBI2": "powerbi.exe",
    "Microsoft-Powerapps": "powerapps.exe",
    "Microsoft-Project": "project.exe",
    "Microsoft-RemoteDesktop3": "mstsc.exe",
    "Microsoft-SharePoint": "sharepoint.exe",
    "Microsoft-Staffhub": "staffhub.exe",
    "Microsoft-StickNotes": "stickynotes.exe",
    "Microsoft-StickNotes2": "stickynotes.exe",
    "Microsoft-Stream": "microsoftstream.exe",
    "Microsoft-SupportCenterTools": "supportcenter.exe",
    "Microsoft-SupportCenterViewer": "supportcenter.exe",
    "Microsoft-TeamsHome": "teams.exe",
    "Microsoft-VisualStudioCode2022": "code.exe",
    "Microsoft-Windows365": "windows365.exe",
    "Microsoft-WindowsFileRecovery": "windowsfilerecovery.exe",
    "Microsoft-WorkFolders": "workfolders.exe",
    "Microsoft-Yammer": "yammer.exe",
    "Microsoft365-MicrosoftStickyNotes": "stickynotes.exe",
    "MicrosoftFSLogixApps": "fslogix.exe",
    "MicrosoftStore-CompanyPortal": "companyportal.exe",
    "MicrosoftStore-DolbyAccess": "dolbyaccess.exe",
    "MicrosoftStore-FeedbackHub": "feedbackhub.exe",
    "MicrosoftStore-Films&TV": "filmsandtv.exe",
    "MicrosoftStore-GetHelp": "gethelp.exe",
    # "MicrosoftStore-Intel\xaeGraphicsCommandCenter": "intelgraphics.exe",  # special char in URL
    "MicrosoftStore-MailandCalendar": "mailandcalendar.exe",
    "MicrosoftStore-Microsoft365": "office365.exe",
    "MicrosoftStore-MicrosoftAccessoryCenter": "accessorycenter.exe",
    "MicrosoftStore-MicrosoftDefender": "defender.exe",
    "MicrosoftStore-MicrosoftJournal": "journal.exe",
    "MicrosoftStore-MicrosoftLoop": "loop.exe",
    "MicrosoftStore-MicrosoftWhiteboard": "whiteboard.exe",
    "MicrosoftStore-OneDrive": "onedrive.exe",
    "MicrosoftStore-Paint3D": "paint3d.exe",
    "MicrosoftStore-PowerAutomate": "powerautomate.exe",
    "MicrosoftStore-PowerBI": "powerbi.exe",
    "MicrosoftStore-PowerBIDesktop": "powerbi.exe",
    "MicrosoftStore-Surface": "surface.exe",
    "MicrosoftStore-Windows365": "windows365.exe",
    "MicrosoftStore-WindowsCamera": "camera.exe",
    "MicrosoftStore-WindowsClock": "clock.exe",
    "MicrosoftStore-WindowsFileRecovery": "windowsfilerecovery.exe",
    "MicrosoftStore-WindowsScan": "windowsscan.exe",
    "MicrosoftStore-WindowsSoundRecorder": "soundrecorder.exe",
    "MicrosoftStore-WireGuardPro": "wireguard.exe",
    "Mimecast": "mimecast.exe",
    "PDFXChangeEditor": "pdfxchange.exe",
    "Plantronics": "plantronics.exe",
    "QlikView": "qlikview.exe",
    "Reincubate-Camo": "camo.exe",
    "Royal-RSX": "royalts.exe",
    "ShareMouse": "sharemouse.exe",
    "TechSmith-Camtasia2": "camtasia.exe",
    "Twitter": "twitter.exe",
    "Xink": "xink.exe",
    "Yubikey-Manager": "yubikeymanager.exe",
    "ZoomRooms": "zoomrooms.exe",
    "Adobe-AcrobatUpdate": "acrobatupdater.exe",
    "Display": "displaysettings.exe",
    "General-Fonts": "fonts.exe",
    "Package": "package.exe",
    "Gpg-Keychain-macOS": "gpgkeychain.exe",
    "Embrava-Connect": "embrava.exe",
    "Linux": "linux.exe",
    "MedicalDirector-Pracsoft": "pracsoft.exe",
    "Microsoft-WindowsLogoColour": "windowslogo.exe",
}


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icons_dir = os.path.join(project_root, "assets", "icons")
    os.makedirs(icons_dir, exist_ok=True)

    repo_url = "https://raw.githubusercontent.com/arkahna/intune-icons/main/icons"

    total = len(ICON_TO_PROCESS)
    downloaded = 0
    skipped = 0

    for icon_name, process_name in sorted(ICON_TO_PROCESS.items()):
        output_path = os.path.join(icons_dir, f"{process_name.lower()}.png")

        if os.path.exists(output_path):
            skipped += 1
            continue

        url = f"{repo_url}/{icon_name}.png"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DayLens/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()

            # Resize to 32x32 using Pillow
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(data))
                img = img.resize((32, 32), Image.LANCZOS)
                img.save(output_path, "PNG")
            except ImportError:
                # No Pillow — save original size
                with open(output_path, "wb") as f:
                    f.write(data)

            downloaded += 1
            if downloaded % 10 == 0:
                print(f"  [{downloaded}/{total}] {icon_name} → {process_name}")
        except Exception as e:
            print(f"  FAIL  {icon_name} — {e}")

    print(f"\nDone: {downloaded} downloaded, {skipped} already existed "
          f"(total mapped: {total})")


if __name__ == "__main__":
    main()
