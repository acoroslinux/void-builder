# Separação das builds

Cada execução do orquestrador usa `workdir/<arquitetura>/build-<identificador>/`.
O rootfs, os bootloaders, o staging da ISO e o `build_host` pertencem a essa
execução. A limpeza e a desmontagem ficam limitadas ao diretório atribuído.

`--no-clean` conserva o diretório para inspeção; não reutiliza o rootfs numa
nova execução. Duas builds não podem escrever simultaneamente no mesmo caminho
de saída. Para manter ambas as imagens, usar nomes de saída diferentes.

Tarballs automáticos são separados por configuração em `cache/tarballs/`.
Os antigos tarballs genéricos deixam de ser selecionados automaticamente.
Um tarball indicado explicitamente com `--use-tarball /caminho` continua a ser
uma escolha do utilizador: o seu conteúdo é incluído na nova build.

As caches XBPS e `custom_packages` continuam a guardar pacotes reutilizáveis;
não são rootfs nem diretórios de staging. A compilação do Calamares continua
a usar o seu ambiente próprio em `workdir/void-packages`.
