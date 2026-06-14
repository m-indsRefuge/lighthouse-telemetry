"""
Memory policy for Lighthouse.

This module will decide what is safe, useful, and appropriate to store as memory.

The engine owns memory decisions.
The model may suggest memory candidates, but this policy must approve or reject them.
"""
