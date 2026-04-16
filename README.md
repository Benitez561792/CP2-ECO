# 🌿 Eco-Awareness 2026: Cashback Progressivo
### Checkpoint 2 | Mastering Relational and Non Relational Databases

---

## 👥 Integrantes
*   **Pedro Peres Benitez** | RM: 561792
*   **Lucca Ramos Mussumecci** | RM: 562027

---

## 🎯 Objetivo do Projeto
Desenvolvimento de um **Motor de Cashback Progressivo** para o evento Eco-Awareness 2026, integrando lógica de banco de dados **Oracle PL/SQL** com uma interface moderna em **Python/Flask**.

---

## 💡 Regras de Negócio (Escalonamento)
O sistema processa automaticamente o estorno de valores para participantes com presença confirmada:
*   **🏆 25% de Cashback:** Para usuários "Ativistas" com mais de 3 presenças.
*   **⭐ 20% de Cashback:** Para inscrições de categoria VIP.
*   **🌱 10% de Cashback:** Taxa piso para os demais participantes.

---

## 🛠️ Destaques Técnicos
*   **Cursor Explícito:** Implementação obrigatória em bloco anônimo para processamento linha a linha.
*   **Rigor Transacional:** Uso de `COMMIT` e `ROLLBACK` para garantir a integridade dos saldos.
*   **Auditoria:** Registro automático de cada operação em tabela de logs.
*   **Integração:** Comunicação entre Python e Oracle via Bind Variables para tratamento de exceções.

---
*FIAP - 2026 | Tecnologia e Sustentabilidade.*
