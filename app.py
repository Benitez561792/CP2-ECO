
import os
from flask import Flask, render_template, redirect, url_for, flash, request
import oracledb
from dotenv import load_dotenv

# Carrega variáveis do .env apenas em ambiente local
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "eco_awareness_fiap_2026_secret")

# ============================================================
#  CONFIGURAÇÃO DA CONEXÃO ORACLE
# ============================================================
DB_CONFIG = {
    "user":     os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "dsn":      os.environ.get("DB_DSN"),
}


def get_connection():
    """Retorna uma conexão ativa com o banco Oracle."""
    return oracledb.connect(**DB_CONFIG)



PLSQL_CASHBACK = """
DECLARE
    -- =========================================================
    --  CURSOR EXPLÍCITO PRINCIPAL
    --  Percorre todas as inscrições com STATUS = 'PRESENT'
    --  ordenadas por usuário e inscrição para consistência
    -- =========================================================
    CURSOR c_participantes IS
        SELECT
            U.ID         AS usuario_id,
            U.NOME       AS nome,
            I.ID         AS inscricao_id,
            I.VALOR_PAGO AS valor_pago,
            I.TIPO       AS tipo
        FROM   USUARIOS  U
        JOIN   INSCRICOES I ON U.ID = I.USUARIO_ID
        WHERE  I.STATUS = 'PRESENT'
        ORDER  BY U.ID, I.ID;

    -- =========================================================
    --  VARIÁVEIS DE CONTROLE
    -- =========================================================
    v_percentual      NUMBER(5,2);
    v_cashback        NUMBER(10,2);
    v_total_presencas NUMBER;
    v_contador        NUMBER        := 0;
    v_total_credito   NUMBER(10,2)  := 0;
    v_motivo          VARCHAR2(400);
    v_regra           VARCHAR2(100);

    -- Exceção customizada para valor de inscrição inválido
    ex_valor_invalido EXCEPTION;
    PRAGMA EXCEPTION_INIT(ex_valor_invalido, -20001);

BEGIN

    -- =========================================================
    --  LOOP DO CURSOR EXPLÍCITO
    --  Cada iteração processa UMA inscrição PRESENT
    -- =========================================================
    FOR r IN c_participantes LOOP

        -- =====================================================
        --  SUBQUERY dentro do loop:
        --  conta o total de presenças (STATUS='PRESENT')
        --  do usuário em TODAS as suas inscrições
        -- =====================================================
        SELECT COUNT(*)
          INTO v_total_presencas
          FROM INSCRICOES
         WHERE USUARIO_ID = r.usuario_id
           AND STATUS     = 'PRESENT';

        -- =====================================================
        --  VALIDAÇÃO: valor pago deve ser estritamente positivo
        --  Lançada antes de qualquer operação de escrita
        -- =====================================================
        IF r.valor_pago <= 0 THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'Valor pago invalido para inscricao ID=' || r.inscricao_id
                || ' | Usuario: ' || r.nome
            );
        END IF;

        -- =====================================================
        --  ESCALONAMENTO DO CASHBACK — regras do enunciado:
        --    1) Ativista exemplar: mais de 3 presenças → 25%
        --    2) Ingresso VIP: TIPO = 'VIP'             → 20%
        --    3) Demais participantes (taxa piso)        → 10%
        -- =====================================================
        IF v_total_presencas > 3 THEN
            v_percentual := 25;
            v_regra      := 'ATIVISTA (>3 presencas)';
        ELSIF UPPER(r.tipo) = 'VIP' THEN
            v_percentual := 20;
            v_regra      := 'INGRESSO VIP';
        ELSE
            v_percentual := 10;
            v_regra      := 'TAXA PISO';
        END IF;

        -- Calcula o cashback desta inscrição (arredondado a 2 casas)
        v_cashback := ROUND(r.valor_pago * v_percentual / 100, 2);

        -- =====================================================
        --  LOG DE AUDITORIA — registra cada operação individual
        -- =====================================================
        v_motivo := 'CASHBACK ' || v_percentual || '% | '
                    || 'Regra: '            || v_regra            || ' | '
                    || 'Presencas totais: ' || v_total_presencas  || ' | '
                    || 'Tipo insc.: '       || r.tipo             || ' | '
                    || 'Valor pago: R$ '    || r.valor_pago       || ' | '
                    || 'Cashback: R$ '      || v_cashback;

        INSERT INTO LOG_AUDITORIA (INSCRICAO_ID, MOTIVO, DATA)
        VALUES (r.inscricao_id, v_motivo, SYSDATE);

        -- =====================================================
        --  ATUALIZA SALDO do usuário com o cashback desta insc.
        -- =====================================================
        UPDATE USUARIOS
           SET SALDO = SALDO + v_cashback
         WHERE ID = r.usuario_id;

        v_contador      := v_contador + 1;
        v_total_credito := v_total_credito + v_cashback;

    END LOOP;
    -- Fim do cursor explícito

    -- Persiste todas as alterações
    COMMIT;

    -- Retorna métricas via Bind Variables para o Python
    :p_usuarios := v_contador;
    :p_total    := v_total_credito;
    :p_status   := 'SUCESSO';
    :p_mensagem := 'Cashback processado para ' || v_contador
                   || ' inscricao(oes). Total creditado: R$ '
                   || TO_CHAR(v_total_credito, 'FM99999990.00');

EXCEPTION
    -- Valor de inscrição inválido (RAISE_APPLICATION_ERROR -20001)
    WHEN ex_valor_invalido THEN
        ROLLBACK;
        :p_usuarios := 0;
        :p_total    := 0;
        :p_status   := 'ERRO';
        :p_mensagem := 'Dados invalidos detectados — ROLLBACK executado. '
                       || SQLERRM;

    -- Qualquer outro erro Oracle inesperado
    WHEN OTHERS THEN
        ROLLBACK;
        :p_usuarios := 0;
        :p_total    := 0;
        :p_status   := 'ERRO';
        :p_mensagem := 'Erro Oracle ' || SQLCODE || ': ' || SQLERRM
                       || ' — ROLLBACK executado.';
END;
"""


# ============================================================
#  HELPERS
# ============================================================

def _enriquecer_usuarios(usuarios: list) -> list:
    """Adiciona CASHBACK_PCT e REGRA a cada registro de usuário."""
    for u in usuarios:
        presencas = u.get("QTD_PRESENT", 0) or 0
        tem_vip   = u.get("TEM_VIP", 0) or 0
        if presencas > 3:
            u["CASHBACK_PCT"] = 25
            u["REGRA"]        = "Ativista"
        elif tem_vip:
            u["CASHBACK_PCT"] = 20
            u["REGRA"]        = "VIP"
        elif presencas > 0:
            u["CASHBACK_PCT"] = 10
            u["REGRA"]        = "Padrão"
        else:
            u["CASHBACK_PCT"] = 0
            u["REGRA"]        = "—"
    return usuarios


SQL_USUARIOS = """
    SELECT
        U.ID,
        U.NOME,
        U.EMAIL,
        U.PRIORIDADE,
        U.SALDO,
        COUNT(CASE WHEN I.STATUS = 'PRESENT' THEN 1 END)                  AS QTD_PRESENT,
        NVL(SUM(CASE WHEN I.STATUS = 'PRESENT' THEN I.VALOR_PAGO END), 0) AS TOTAL_PAGO,
        MAX(CASE WHEN I.STATUS = 'PRESENT' AND UPPER(I.TIPO) = 'VIP'
                 THEN 1 ELSE 0 END)                                        AS TEM_VIP
    FROM   USUARIOS  U
    LEFT JOIN INSCRICOES I ON U.ID = I.USUARIO_ID
    GROUP  BY U.ID, U.NOME, U.EMAIL, U.PRIORIDADE, U.SALDO
    ORDER  BY {order}
"""

SQL_STATS = """
    SELECT
        COUNT(DISTINCT U.ID)                                                AS TOTAL_USUARIOS,
        COUNT(CASE WHEN I.STATUS = 'PRESENT' THEN 1 END)                   AS TOTAL_PRESENT,
        NVL(SUM(CASE WHEN I.STATUS = 'PRESENT' THEN I.VALOR_PAGO END), 0)  AS VOLUME_TOTAL,
        NVL(SUM(U.SALDO), 0)                                                AS CASHBACK_TOTAL_PAGO
    FROM USUARIOS U
    LEFT JOIN INSCRICOES I ON U.ID = I.USUARIO_ID
"""

SQL_LOGS = """
    SELECT
        L.ID,
        L.INSCRICAO_ID,
        L.MOTIVO,
        TO_CHAR(L.DATA, 'DD/MM/YYYY HH24:MI:SS') AS DATA_STR
    FROM   LOG_AUDITORIA L
    ORDER  BY L.ID DESC
    FETCH FIRST 50 ROWS ONLY
"""


def _fetch_all(cur, sql: str) -> list:
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_one(cur, sql: str) -> dict:
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    row  = cur.fetchone()
    return dict(zip(cols, row)) if row else {}


# ============================================================
#  ROTA: PÁGINA INICIAL
# ============================================================
@app.route("/")
def index():
    try:
        conn = get_connection()
        cur  = conn.cursor()

        usuarios = _enriquecer_usuarios(
            _fetch_all(cur, SQL_USUARIOS.format(order="U.PRIORIDADE DESC, U.NOME"))
        )
        stats = _fetch_one(cur, SQL_STATS)

        cur.close()
        conn.close()

        return render_template("index.html", usuarios=usuarios, stats=stats)

    except oracledb.DatabaseError as e:
        error, = e.args
        flash(f"Erro Oracle {error.code}: {error.message}", "error")
        return render_template("index.html", usuarios=[], stats={})


# ============================================================
#  ROTA: PROCESSAR CASHBACK — executa o bloco PL/SQL
# ============================================================
@app.route("/processar", methods=["POST"])
def processar_cashback():
    try:
        conn = get_connection()
        cur  = conn.cursor()

      
        p_usuarios = cur.var(int)
        p_total    = cur.var(float)
        p_status   = cur.var(str)
        p_mensagem = cur.var(str)

        cur.execute(PLSQL_CASHBACK, {
            "p_usuarios": p_usuarios,
            "p_total":    p_total,
            "p_status":   p_status,
            "p_mensagem": p_mensagem,
        })

        resultado = {
            "usuarios": p_usuarios.getvalue() or 0,
            "total":    p_total.getvalue()    or 0.0,
            "status":   p_status.getvalue()   or "ERRO",
            "mensagem": p_mensagem.getvalue() or "Sem retorno do bloco PL/SQL.",
        }

        usuarios = _enriquecer_usuarios(
            _fetch_all(cur, SQL_USUARIOS.format(order="U.SALDO DESC, U.NOME"))
        )
        logs  = _fetch_all(cur, SQL_LOGS)
        stats = _fetch_one(cur, SQL_STATS)

        cur.close()
        conn.close()

        return render_template("resultado.html",
                               resultado=resultado,
                               usuarios=usuarios,
                               logs=logs,
                               stats=stats)

    except oracledb.DatabaseError as e:
        error, = e.args
        flash(f"Erro Oracle {error.code}: {error.message}", "error")
        return redirect(url_for("index"))


# ============================================================
#  ROTA: RESET — zera saldos e limpa logs para nova rodada
# ============================================================
@app.route("/reset", methods=["POST"])
def reset():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute("DELETE FROM LOG_AUDITORIA")
        cur.execute("UPDATE USUARIOS SET SALDO = 0")
        conn.commit()
        cur.close()
        conn.close()
        flash("Dados resetados com sucesso! Saldos zerados e logs limpos.", "success")
    except oracledb.DatabaseError as e:
        error, = e.args
        flash(f"Erro ao resetar: {error.message}", "error")

    return redirect(url_for("index"))


# ============================================================
#  ENTRY POINT LOCAL
# ============================================================
if __name__ == "__main__":
    app.run(debug=True, port=5000)
