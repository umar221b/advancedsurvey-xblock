## Localization targets

extract_translations: ## extract strings to be translated, outputting .po files
	i18n_tool extract

compile_translations: ## compile translation files, outputting .mo files for each supported language
	i18n_tool generate
	# python manage.py compilejsi18n --advncedsurveyi18n --output $(JS_TARGET)

move_translations:
	mv locale/en/LC_MESSAGES/django-partial.po translations/en/LC_MESSAGES/text.po
	mv locale/en/LC_MESSAGES/django-partial.mo translations/en/LC_MESSAGES/text.mo
