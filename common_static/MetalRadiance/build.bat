:loop

python -m scss scss/main.scss -o metalradiance.css -I scss -C 
rem --debug-info -C
  
rem ;;;;python -m scss -w scss --recursive -o css -I scss
rem ; --debug-info 

TIMEOUT /T 10
goto loop