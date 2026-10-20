QIDI Box
==========================================

Printers fitted with a QIDI Box (for example the Q2) expose it to Klipper as
``box_stepper slotN`` and ``box_extras`` objects. Newer QIDI firmware reports
decoded per-slot details in ``box_extras.boxes``; older firmware only keeps the
filament chosen for each slot in ``save_variables`` as numeric codes. Both
formats are supported.

Filament sensors
-----------------------------

For every ``box_stepper slotN`` object (when ``save_variables`` is available)
we create a **Box Slot N Filament** sensor.

-  The state is the filament name (for example ``PLA Basic``) or ``Empty`` when
   the slot's runout switch is triggered. With older firmware, a code the
   integration does not know is shown as ``Unknown (code)``.
-  Attributes:

   -  ``color``: hex colour, for example ``#F28636``
   -  ``vendor``: for example ``QIDI`` or ``Generic``
   -  ``filament_type``: for example ``PLA`` (newer firmware only)
   -  ``min_temp`` / ``max_temp``: recommended nozzle temperature range in °C
      (newer firmware only)
   -  ``filament_id``, ``color_id`` and ``slot_state``: the raw values stored
      by the printer
   -  ``runout``: ``true`` when the slot's runout switch reports no filament

With newer firmware the name, type, vendor, colour and temperatures come
straight from ``box_extras.boxes[N].filament_info``. With older firmware they
are decoded from the lookup tables in the printer's own
``officiall_filas_list.cfg``, which are built into the integration.

.. note::
   An empty slot keeps reporting the details of the last spool that was loaded,
   so check the state (or ``runout``) before showing them.

Drying binary sensor
-----------------------------

For every box that reports a drying state we create a **Box N Drying** binary
sensor that is on while the box is drying. Newer firmware reports this per box
in ``box_extras.boxes`` (only boxes that are online get a sensor); older
firmware uses ``box_extras.box_drying_state``.

Filament change sensors
-----------------------------

Firmware with the Box V2 ``multi_color_controller`` object also gets:

-  **Box Filament Change**: what the box is doing during a colour change.

   -  The state is ``idle``, ``changing`` (a change is about to start, or the
      nozzle is being purged afterwards), ``starting``, ``cutting``,
      ``unloading``, ``loading`` or ``paused``. Other firmware steps are shown
      in lower case without the ``BOX_`` prefix.
   -  Attributes:

      -  ``target_slot``: the slot being loaded (1-based), while a change runs
      -  ``loaded_slot``: the slot currently in the toolhead (1-based), or
         empty when nothing (or the external spool) is loaded
      -  ``step`` and ``steps``: the raw current step and the step queue, for
         example ``BOX_CUT``, ``BOX_UNLOAD``, ``BOX_LOAD``
      -  ``flow_id``, ``tool_change`` and ``warnings``: the raw values reported
         by the printer

-  **Box Warnings**: the number of warnings the box reports, with the raw
   warnings in the ``warnings`` attribute.

A change on a Q2 takes about a minute and a half: ``changing`` for a few
seconds, then ``cutting``, ``unloading`` and ``loading``, and ``changing`` again
while the new filament is purged.

Temperature and humidity
-----------------------------

The box's temperature and humidity are already available through the
``heater_generic`` and ``aht20_f`` sensors described in :doc:`sensors`
(for example ``heater_box1``).

Dashboard example
-----------------------------

A Markdown card that lists every slot with a coloured dot, the filament, vendor,
temperature range and colour. Replace ``q2`` with your printer's entity prefix.

.. code-block:: yaml

   type: markdown
   content: |
     {% set slots = ['sensor.q2_box_slot_1_filament',
                     'sensor.q2_box_slot_2_filament',
                     'sensor.q2_box_slot_3_filament',
                     'sensor.q2_box_slot_4_filament'] %}
     {% for s in slots %}
     {% if states(s) == 'Empty' %}<font color="#888888">○</font> **Slot {{ loop.index }}** · Empty<br>
     {% else %}<font color="{{ state_attr(s, 'color') or '#888888' }}">●</font> **Slot {{ loop.index }}** · {{ states(s) }} · {{ state_attr(s, 'vendor') or 'Unknown vendor' }}{% set lo = state_attr(s, 'min_temp') %}{% set hi = state_attr(s, 'max_temp') %}{% if lo and hi %} · {{ lo }}–{{ hi }} °C{% endif %} · {{ state_attr(s, 'color') or '' }}<br>
     {% endif %}
     {% endfor %}
