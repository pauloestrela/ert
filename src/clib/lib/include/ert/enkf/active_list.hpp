#ifndef ERT_ACTIVE_LIST_H
#define ERT_ACTIVE_LIST_H

#include <stdio.h>

#include <vector>

#include <ert/enkf/enkf_types.hpp>

/**
   This enum is used when we are setting up the dependencies between
   observations and variables. The modes all_active and inactive are
   sufficient information, for the values partly active we need
   additional information.

   The same type is used both for variables (PRESSURE/PORO/MULTZ/...)
   and for observations.
*/
typedef enum {
    /** The variable/observation is fully active, i.e. all cells/all faults/all .. */
    ALL_ACTIVE = 1,
    /** Partly active - must supply additonal type spesific information on what is active.*/
    PARTLY_ACTIVE = 3
} active_mode_type;

class ActiveList {
public:
    const std::vector<int> &index_list() const;
    const int *active_list_get_active() const;
    active_mode_type getMode() const;
    int active_size(int default_size) const;
    void add_index(int index);
    bool operator==(const ActiveList &other) const;

private:
    std::vector<int> m_index_list;
    active_mode_type m_mode = ALL_ACTIVE;
};

#endif
