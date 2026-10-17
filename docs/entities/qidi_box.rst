QIDI Box
==========================================

Printers fitted with a QIDI Box (for example the Q2) expose it to Klipper as
``box_stepper slotN`` and ``box_extras`` objects, and keep the filament chosen
for each slot in ``save_variables`` as numeric codes.

Filament sensors
-----------------------------

For every ``box_stepper slotN`` object (when ``save_variables`` is available)
we create a **Box Slot N Filament** sensor.

-  The state is the filament name (for example ``PLA Basic``), ``Empty`` when
   the slot's runout switch is triggered, or ``Unknown (code)`` for a code the
   integration does not know.
-  Attributes: ``color`` (hex), ``vendor``, ``filament_id``, ``color_id``,
   ``slot_state`` (the raw value stored by the printer) and ``runout``.

The names, colours and vendors come from the lookup tables in the printer's own
``officiall_filas_list.cfg``, which are built into the integration.

Drying binary sensor
-----------------------------

For every box listed in ``box_extras.box_drying_state`` we create a
**Box N Drying** binary sensor that is on while the box reports a non-idle
drying state.

Temperature and humidity
-----------------------------

The box's temperature and humidity are already available through the
``heater_generic`` and ``aht20_f`` sensors described in :doc:`sensors`
(for example ``heater_box1``).
