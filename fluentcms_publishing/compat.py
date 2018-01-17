# -*- coding: utf-8 -*-

import django


def get_m2m_with_model(model):
    if django.VERSION < (1, 8):
        return model._meta.get_m2m_with_model()
    else:
        return [
            (f, f.model if f.model != model else None)
            for f in model._meta.get_fields()
            if f.many_to_many and not f.auto_created
        ]


def get_all_related_many_to_many_objects(opts):
    if django.VERSION < (1, 8):
        return opts.get_all_related_many_to_many_objects()
    else:
        return [f for f in opts.get_fields(include_hidden=True) if f.many_to_many and f.auto_created]


def get_all_related_objects(opts, local_only=False, include_hidden=False, include_proxy_eq=False):
    if django.VERSION < (1, 8):
        return opts.get_all_related_objects(
            local_only=local_only, include_hidden=include_hidden, include_proxy_eq=include_proxy_eq)
    else:
        return [r for r in opts.related_objects if not r.field.many_to_many]
