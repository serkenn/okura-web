"""okura-web：okura-gov（判定コア・記録層）の外側を作る、家族のための Web アプリ。

- Web のサーバーは標準ライブラリだけで動く（サードパーティのパッケージを使わない）。
- 判定コア（okura_core。OpenFisca、AGPL）と記録層（okura_records。beancount、GPL）は import しない。
  別の仮想環境のサブプロセスとして `-I -X utf8` で起動し、JSON だけでやり取りする（okura-gov SCOPE §6-2）。
"""

__version__ = "0.1.0"
