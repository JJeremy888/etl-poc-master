@echo on
cd /d C:\Users\DELL\Desktop\etl-poc-master
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/JJeremy888/etl-poc-master.git
git push -u origin main
@echo off
pause
