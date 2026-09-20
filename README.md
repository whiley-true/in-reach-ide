# in-reach-ide

A desktop IDE for Halo: Reach Megalo game variants -- a VSCode-shaped editor over the
[`in-reach`](https://pypi.org/project/in-reach/) library: project explorer, script editor with Megalo syntax colouring,
a Problems tab, a Scripts view (modules, blocks, storage budget, fusion), version history, Kanban, search, and one-click
build, RVT and MCC launch.

```
pip install in-reach-ide
in-reach-ide            # or: in-reach run
```

Windows only. The command line (`in-reach build`, `check`, `link`, `show`, ...) is in the `in-reach` package, which this
one depends on; everything the IDE does to a script project you can also do -- and automate -- from there.

## Development

```
pip install -e ../in-reach      # or a released in-reach
pip install -e ".[dev]"
python -m pytest tests -q
```

Licensed under the GPLv3, like `in-reach`.
