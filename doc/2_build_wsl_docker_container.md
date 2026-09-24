## Build the project as a single docker container
In each submodule, I tried to document stuff properly using docstrings, those could be an intermediate solution for the documentation.

It would be a bad idea to post the entire instruction here in this README file, besides, I still have to work on a detailed user instruction, this will later be placed in [doc](./doc).

Please step over for more information.

To build the project as a docker container via Windows WSL2 (Docker Desktop), just do the following things in a 
terminal:
    
    cd <your working dir>/pyiec61850DER/pyiec61850DER
    cd ./container/build/windows # if you build the container using docker desktop
    docker-compose up 

To build the project as a docker container on a linux platform, like the container station of QNAP NAS, just copy the following repo completely into the directory where all container applications are stored, and then start the container application in container station.

    <your working dir>/pyiec61850DER/pyiec61850DER

You may have to copy the docker-compose file from

    ./container/build/linux

to the root directory of your container application before starting the docker-compose process.
