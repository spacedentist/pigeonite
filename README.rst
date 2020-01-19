pykzee
======

.. image:: https://travis-ci.org/spacedentist/pykzee.svg?branch=master
   :target: https://travis-ci.org/spacedentist/pykzee

.. image:: https://badges.gitter.im/pykzee/community.svg
   :alt: Chat on Gitter
   :target: https://gitter.im/pykzee/community?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge


Introduction
------------

Pykzee is an engine that allows plug-ins to operate on a JSON-like state tree.
Each plug-in can publish its internal state as part of the global state tree,
and can subscribe to changes of any part of the tree. Plug-ins can also send
commands between each other.

The original purpose of Pykzee is to build home automations systems, but it
may well be useful in other contexts.

Installation
------------

.. code-block:: shell-session

   $ pip install pykzee

Pykzee depends on *pyimmutable*, which will automatically be installed by pip if it is not present. Installation of pyimmutable may require a C++17 compiler on the host system.

Example Use
-----------

.. code-block:: shell-session

   mkdir pykzee-config
   cd pykzee-config
   pykzee

The ``pykzee`` executable will run forever. Because it is run in an empty directory, it loads an empty state (``{}``) from disk, and since no plug-ins are loaded, nothing will ever change the state. Press ``CTRL-C`` to stop the pykzee process. Then try this:

.. code-block:: shell-session

   mkdir plugins
   echo '{"__plugin__": "pykzee.core:StateLoggerPlugin", "pretty": true}' >plugins/StateLogger.json
   pykzee

Launching ``pykzee`` again now yields some output on the terminal. What you see is the StateLoggerPlugin printing the complete state tree. It will do this again every time the state changes. If you have a look at the output, you will notice a few things: firstly, the state has two keys on the top level: `plugins` and `sys`. The `plugins` key was created by you when you created a directory of the same name. The `sys` key is added by pykzee itself. Pykzee publishes information on the internal state of the engine in the `sys` entry. Going back to the `plugins` key, you should see that it contains an object which in turn contains a single entry `StateLogger`. It is named like that because you placed a file `StateLogger.json` inside the `plugins` directory. However, the contents of the `StateLogger` entry in your state tree does not match what you put inside the `StateLogger.json` file. It would, if you hadn't used the special key `__plugin__` in that file.

Pykzee instantiates a plug-in wherever it finds an object with a ``__plugin__`` key in the original state tree. The value of the ``__plugin__`` key must be a Python class (in ``module:class`` notation like ``foo.bar.baz:classname``, referring to the class ``classname`` in the module ``foo.bar.baz``). The object containing the ``__plugin__`` key will get replaced in the state tree with the state published by the plug-in. The original object may have keys other than ``__plugin__``, and those can be used to configure the plug-in, see for example the ``pretty`` key in this example, which makes the StateLoggerPlugin output the state in pretty printed form. The StateLoggerPlugin does not publish any state, so in the state tree (that we can see now in the terminal output) it says `"StateLogger": null`.

While the ``pykzee`` process is still active in your terminal, open another terminal window, enter the same ``pykzee-config`` directory and add another file:

.. code-block:: shell-session

   echo '{"hello": "world"}' >test.json

The pykzee process will notice the change in the configuration file directory and reload the configuration. Go back to your first terminal window, and you will see that the StateLoggerPlugin has printed the new state tree, which now includes a field named ``test`` with the contents ``{"hello": "world"}``.

Plug-ins Distributed with the Core Package
------------------------------------------

The ``pykzee`` package comes with three plug-ins included:

* ``pykzee.core.StateLoggerPlugin``: logs the complete state tree on every change.
* ``pykzee.core.CodePlugin``: executes a snippet of Python code with access to the state tree.

Further Reading
---------------

Pykzee only becomes useful once further plug-ins are installed. Please have a look at the ``pykzee-inspector`` plug-in, which contains a web server that serves a browser application for inspecting the Pykzee state.
