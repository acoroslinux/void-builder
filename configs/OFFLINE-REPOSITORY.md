# Repositório offline

Ativar com `--with-offline-repo`. Editar `configs/offline-packages.txt`
para escolher ferramentas e drivers opcionais, um nome XBPS por linha.
Esta lista é independente dos perfis de pacotes do sistema live.
`--offline-repo-packages pacote1,pacote2` substitui a lista nessa build.
Os pacotes devem existir nos repositórios configurados para a arquitetura.

Na ISO, os arquivos ficam em `/repo`, ao lado de `/LiveOS`, fora do SquashFS.
`repo/selected-packages.txt` lista os pedidos e `repo/packages.txt` lista os
arquivos incluídos com versões, incluindo todas as dependências necessárias.
As dependências são resolvidas com uma base de dados vazia; não se excluem
bibliotecas só por já estarem instaladas no live.

Na sessão live com Dracut, o repositório está em `/run/initramfs/live/repo`.
Para instalar usando exclusivamente o repositório offline:

```sh
sudo xbps-install -i -R /run/initramfs/live/repo nome-do-pacote
```

O repositório offline é incorporado apenas em imagens ISO. Em formatos como
tarball ou imagem de disco, `--with-offline-repo` é ignorado com um aviso para
evitar aumentar o artefacto ou deixar uma configuração `/repo` incompleta.
