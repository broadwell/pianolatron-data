#!/usr/bin/env python3

""" Delete all parsing files associated with the given DRUID """
""" NOTE that for now this does not delete the downloaded    """
""" MODS and IIIF metadata about the DRUID (these rarely     """
""" change and should be handled manually if so), nor the    """
""" binasc or report files for the DRUID, because these are  """
""" overwritten each time build-metadata.py is run.          """

import logging
import sys
from pathlib import Path

druid = sys.argv[1]

Path(f"txt/{druid}.txt").unlink(missing_ok=True)
Path(f"json/{druid}.json").unlink(missing_ok=True)
Path(f"midi/{druid}.mid").unlink(missing_ok=True)
Path(f"midi/raw/{druid}_raw.mid").unlink(missing_ok=True)
Path(f"midi/note/{druid}_note.mid").unlink(missing_ok=True)
Path(f"midi/exp/{druid}_exp.mid").unlink(missing_ok=True)
Path(f"txt/{druid}.txt").unlink(missing_ok=True)
