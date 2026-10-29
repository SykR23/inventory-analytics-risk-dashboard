@echo off
REM ===========================================================================
REM Builds a standalone Windows .exe of the dashboard (no Python needed to run).
REM Run this once on a machine that already has the project set up.
REM Output: dist\InventoryDashboard\InventoryDashboard.exe
REM ===========================================================================
cd /d "%~dp0"

echo [1/4] Ensuring build tools are installed...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip pyinstaller || goto :err

echo [2/4] Building the executable (this can take 5-15 minutes)...
".venv\Scripts\python.exe" -m PyInstaller app.spec --noconfirm --clean || goto :err

echo [3/4] Placing config.yaml and data next to the exe...
copy /Y "config.yaml" "dist\InventoryDashboard\config.yaml" >nul
if exist "data\Shirts" (
    xcopy "data\Shirts" "dist\InventoryDashboard\data\Shirts\" /E /I /Y >nul
)

echo [4/4] Writing a quick-start note...
> "dist\InventoryDashboard\HOW TO USE.txt" echo Double-click InventoryDashboard.exe to launch the dashboard.
>> "dist\InventoryDashboard\HOW TO USE.txt" echo It opens in your web browser at http://localhost:8501
>> "dist\InventoryDashboard\HOW TO USE.txt" echo.
>> "dist\InventoryDashboard\HOW TO USE.txt" echo To use your own data, replace the folders inside the data\ folder
>> "dist\InventoryDashboard\HOW TO USE.txt" echo (keep the layout: data\Category\Year\MonthName.xlsx) and relaunch.
>> "dist\InventoryDashboard\HOW TO USE.txt" echo Close the black console window to stop the dashboard.

echo.
echo DONE. Share the whole folder:  dist\InventoryDashboard
echo Run it with:                   dist\InventoryDashboard\InventoryDashboard.exe
goto :eof

:err
echo.
echo BUILD FAILED. See the messages above.
exit /b 1
