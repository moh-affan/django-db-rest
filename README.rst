==============
DJANGO DB REST
==============

Django DB Rest is a library that integrate Django Rest Framework to Django Model

Quick start
-----------

1. Add "django-db-rest" to your INSTALLED_APPS setting like this::

    INSTALLED_APPS = [
        ...
        'django-db-rest',
    ]

2. Make your viewset extends from ModelViewSet imported from django-db-rest/viewsets package::

    class MyViewSet(ModelViewSet),

3. Add ``model_class`` property to your viewsets class.

4. If your model is one to many, add ``detail_model_class`` and  ``fkey_detail``. ``detail_model_class`` is your many model while ``fkey_detail`` is foreign key name of your parent model

5. Makesure that you have django and djangorestframework package installed