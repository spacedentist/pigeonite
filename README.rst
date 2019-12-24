pykzee
======

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

The ``pykzee`` executable will run forever. Because it is run in an empty directory, the internal state is empty (``{}``), and since no plug-ins are loaded, nothing will ever change the state. Press ``CTRL-C`` to stop the pykzee process. Then try this:

.. code-block:: shell-session

   echo '{"__plugin__": "core-plugin"}' >core.json
   mkdir plugins
   echo '{"__plugin__": "pykzee.core.StateLoggerPlugin", "pretty": true}' >plugins/StateLogger.json
   pykzee

Launching ``pykzee`` again now yields some output on the terminal. What you see is the StateLoggerPlugin printing the complete state tree. It will do this again every time the state changes.

Pykzee instantiates a plug-in wherever it finds an object with a ``__plugin__`` key in the original state tree. The value of the ``__plugin__`` key must be a Python class (in dotted notation like ``foo.bar.baz.classname``, referring to the class ``classname`` in the module ``foo.bar.baz``) or the special value ``core-plugin``. The object containing the ``__plugin__`` key will get replaced in the state tree with the state published by the plug-in. The original object may have keys other than ``__plugin__``, and those can be used to configure the plug-in, see for example the ``pretty`` key in this example, which make the StateLoggerPlugin output the state in pretty printed form.

While the ``pykzee`` process is still active in your terminal, open another terminal window, enter the same ``pykzee-config`` directory and add another file:

.. code-block:: shell-session

   echo '{"hello": "world"}' >test.json

The pykzee process will notice the change in the configuration file directory and reload the configuration. Go back to your first terminal window, and you will see that the StateLoggerPlugin has printed the new state tree, which now includes a field named ``test`` with the contents ``{"hello": "world"}``.

Plug-ins Distributed with the Core Package
------------------------------------------

The ``pykzee`` package comes with three plug-ins included:

* ``core-plugin``: publishes information about the Pykzee engine itself, e.g. which plug-ins are loaded.
* ``pykzee.core.StateLoggerPlugin``: logs the complete state tree on every change.
* ``pykzee.core.CodePlugin``: executes a snippet of Python code with access to the state tree.

Further Reading
---------------

Pykzee only becomes useful once further plug-ins are installed. Please have a look at the ``pykzee-inspector`` plug-in, which contains a web server that serves a browser application for inspecting the Pykzee state.
