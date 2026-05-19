.PHONY: help up down down-v logs ps restart docker-prune docker-clean reset

COMPOSE := docker compose

help:
	@echo make up            - sobe os servicos (detached)
	@echo make down          - para e remove containers
	@echo make down-v        - para e remove containers e volumes
	@echo make logs          - acompanha logs dos servicos
	@echo make ps            - lista status dos servicos
	@echo make restart       - reinicia os servicos
	@echo make docker-prune  - remove recursos Docker nao usados (leve)
	@echo make docker-clean  - remove imagens, containers, redes e volumes nao usados
	@echo make reset         - down-v + docker-clean + up

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

down-v:
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

restart: down up

dp:
	docker system prune -f && docker system prune -a --volumes -f


r: down-v docker-clean up
