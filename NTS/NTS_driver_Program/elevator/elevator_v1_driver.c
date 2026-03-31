#include <assert.h>
#include <stdio.h>

#define NFLOORS     5
#define MAX_RIDERS  10
#define MAXINT      100007

int stops_1[MAX_RIDERS + 1];
int stops_2[MAX_RIDERS + 1];

int nriders;
int nstops;

int m_1[NFLOORS + 1][MAX_RIDERS + 1];
int m_2[NFLOORS + 1][MAX_RIDERS + 1];

extern int nondet_int();

int min_1(int a, int b) {
    return (a < b) ? a : b;
}

int min_2(int a, int b) {
    return (a < b) ? b : b; // Faulty
}

int floors_walked_1(int prev, int curr) {
    int steps = 0;
    for (int i = 1; i <= nriders; i++)
        if (stops_1[i] > prev && stops_1[i] <= curr)
            steps += min_1(stops_1[i] - prev, curr - stops_1[i]);
    return steps;
}

int floors_walked_2(int prev, int curr) {
    int steps = 0;
    for (int i = 1; i <= nriders; i++)
        if (stops_2[i] > prev && stops_2[i] <= curr)
            steps += min_2(stops_2[i] - prev, curr - stops_2[i]);
    return steps;
}

int optimize_floors_1() {
    for (int i = 0; i <= NFLOORS; i++)
        m_1[i][0] = floors_walked_1(0, MAXINT);

    for (int j = 1; j <= nstops; j++)
        for (int i = 0; i <= NFLOORS; i++) {
            m_1[i][j] = MAXINT;
            for (int k = 0; k <= i; k++) {
                int cost = m_1[k][j - 1] - floors_walked_1(k, MAXINT)
                         + floors_walked_1(k, i) + floors_walked_1(i, MAXINT);
                if (cost < m_1[i][j])
                    m_1[i][j] = cost;
            }
        }

    int laststop = 0;
    for (int i = 1; i <= NFLOORS; i++)
        if (m_1[i][nstops] < m_1[laststop][nstops])
            laststop = i;
    return laststop;
}

int optimize_floors_2() {
    for (int i = 0; i <= NFLOORS; i++)
        m_2[i][0] = floors_walked_2(0, MAXINT);

    for (int j = 1; j <= nstops; j++)
        for (int i = 0; i <= NFLOORS; i++) {
            m_2[i][j] = MAXINT;
            for (int k = 0; k <= i; k++) {
                int cost = m_2[k][j - 1] - floors_walked_2(k, MAXINT)
                         + floors_walked_2(k, i) + floors_walked_2(i, MAXINT);
                if (cost < m_2[i][j])
                    m_2[i][j] = cost;
            }
        }

    int laststop = 0;
    for (int i = 1; i <= NFLOORS; i++)
        if (m_2[i][nstops] < m_2[laststop][nstops])
            laststop = i;
    return laststop;
}

int test_driver() {

    /*for (int i = 0; i <= NFLOORS; i++) {
        for (int j = 0; j < MAX_RIDERS; j++) {
            assert(m_1[i][j] == 0);
            assert(m_2[i][j] == 0);
        }
    }*/
    nriders=nondet_int();
	nstops=nondet_int();
    __CPROVER_assume(nriders >= 1 && nriders <= 10);
    __CPROVER_assume(nstops >= 1 && nstops <= 5);
    for (int i = 1; i <= nriders; i++) {
        int val = i; // Ensure increasing diverse stops
        stops_1[i] = val;
        stops_2[i] = val;
    }

    int last1 = optimize_floors_1();
    int last2 = optimize_floors_2();

    int cost1 = m_1[last1][nstops];
    int cost2 = m_2[last2][nstops];

    //assert((cost1 != cost2));
    assert((cost1 == cost2)); 
    return 0;
}
